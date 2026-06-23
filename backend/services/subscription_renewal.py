import os
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from services import billing as billing_service


def _row_mapping(row):
    if not row:
        return None
    return row._mapping if hasattr(row, "_mapping") else row


def _rows(result):
    return [_row_mapping(row) for row in result.fetchall()]


def run_subscription_renewals(db: Session, limit: int = 50, charge_client=None):
    targets = _find_due_renewal_subscriptions(db, limit=limit)
    results = []

    for subscription in targets:
        try:
            result = _process_subscription_renewal(
                db=db,
                subscription=subscription,
                charge_client=charge_client,
            )
            db.commit()
            results.append(result)
        except Exception as exc:
            db.rollback()
            results.append({
                "subscription_id": str(subscription["subscription_id"]),
                "status": "failed",
                "failure_code": "renewal_exception",
                "failure_message": str(exc),
            })

    return {
        "processed": len(results),
        "results": results,
    }


def run_scheduled_downgrades(db: Session, limit: int = 50, charge_client=None):
    targets = _find_due_scheduled_downgrades(db, limit=limit)
    results = []

    for plan_change in targets:
        try:
            result = _process_scheduled_downgrade(
                db=db,
                plan_change=plan_change,
                charge_client=charge_client,
            )
            db.commit()
            results.append(result)
        except Exception as exc:
            db.rollback()
            results.append({
                "plan_change_id": str(plan_change["plan_change_id"]),
                "status": "failed",
                "failure_code": "scheduled_downgrade_exception",
                "failure_message": str(exc),
            })

    return {
        "processed": len(results),
        "results": results,
    }


def _find_due_renewal_subscriptions(db: Session, limit: int = 50):
    result = db.execute(
        text("""
            SELECT
                s.subscription_id,
                s.user_id,
                s.plan_id,
                s.billing_key_id,
                s.next_billing_at,
                p.plan_code,
                p.plan_name,
                p.price_amount,
                p.credits
            FROM subscriptions s
            JOIN plans p ON p.plan_id = s.plan_id
            WHERE s.status = 'active'
              AND s.auto_renew = true
              AND s.cancel_at_period_end = false
              AND s.next_billing_at <= NOW()
              AND p.price_amount > 0
            ORDER BY s.next_billing_at ASC, s.created_at ASC
            LIMIT :limit
            FOR UPDATE OF s SKIP LOCKED
        """),
        {"limit": limit},
    )
    return _rows(result)


def _find_due_scheduled_downgrades(db: Session, limit: int = 50):
    result = db.execute(
        text("""
            SELECT
                pc.plan_change_id,
                pc.user_id,
                pc.subscription_id AS from_subscription_id,
                pc.from_subscription_id AS source_subscription_id,
                pc.to_plan_id,
                pc.effective_at,
                p.plan_code,
                p.plan_name,
                p.price_amount,
                p.credits
            FROM subscription_plan_changes pc
            JOIN plans p ON p.plan_id = pc.to_plan_id
            WHERE pc.change_type = 'downgrade'
              AND pc.status = 'scheduled'
              AND pc.effective_at <= NOW()
            ORDER BY pc.effective_at ASC, pc.created_at ASC
            LIMIT :limit
            FOR UPDATE OF pc SKIP LOCKED
        """),
        {"limit": limit},
    )
    return _rows(result)


def _process_subscription_renewal(db: Session, subscription, charge_client=None):
    billing_key = billing_service.get_active_billing_key_for_charge(
        db=db,
        user_id=subscription["user_id"],
        billing_key_id=subscription.get("billing_key_id"),
    )
    if not billing_key:
        attempt = _record_billing_attempt(
            db=db,
            subscription=subscription,
            status="failed",
            failure_code="billing_key_missing",
            failure_message="Active billing key was not found.",
        )
        db.execute(
            text("""
                UPDATE subscriptions
                SET
                    billing_status = 'billing_key_missing',
                    updated_at = NOW()
                WHERE subscription_id = :subscription_id
            """),
            {"subscription_id": subscription["subscription_id"]},
        )
        return {
            "subscription_id": str(subscription["subscription_id"]),
            "status": "failed",
            "billing_attempt_id": str(attempt["billing_attempt_id"]) if attempt else None,
            "failure_code": "billing_key_missing",
        }

    charge = _charge_subscription(
        subscription=subscription,
        billing_key=billing_key,
        charge_client=charge_client,
    )
    if not charge.get("success"):
        attempt = _record_billing_attempt(
            db=db,
            subscription=subscription,
            billing_key_id=billing_key["billing_key_id"],
            status="failed",
            failure_code=charge.get("failure_code") or "billing_failed",
            failure_message=charge.get("failure_message"),
            pg_transaction_id=charge.get("pg_transaction_id"),
        )
        db.execute(
            text("""
                UPDATE subscriptions
                SET
                    billing_status = 'failed',
                    updated_at = NOW()
                WHERE subscription_id = :subscription_id
            """),
            {"subscription_id": subscription["subscription_id"]},
        )
        return {
            "subscription_id": str(subscription["subscription_id"]),
            "status": "failed",
            "billing_attempt_id": str(attempt["billing_attempt_id"]) if attempt else None,
            "failure_code": charge.get("failure_code") or "billing_failed",
        }

    payment = _insert_renewal_payment(
        db=db,
        subscription=subscription,
        billing_key_id=billing_key["billing_key_id"],
        charge=charge,
    )
    updated_subscription = _extend_subscription_period(
        db=db,
        subscription_id=subscription["subscription_id"],
        payment_id=payment["payment_id"],
    )
    attempt = _record_billing_attempt(
        db=db,
        subscription=subscription,
        billing_key_id=billing_key["billing_key_id"],
        payment_id=payment["payment_id"],
        status="success",
        pg_transaction_id=charge.get("pg_transaction_id"),
    )
    db.execute(
        text("""
            UPDATE billing_keys
            SET
                last_used_at = NOW(),
                updated_at = NOW()
            WHERE billing_key_id = :billing_key_id
        """),
        {"billing_key_id": billing_key["billing_key_id"]},
    )

    from services.subscription import award_pending_ai_refund
    award_pending_ai_refund(db, subscription["user_id"])

    return {
        "subscription_id": str(subscription["subscription_id"]),
        "status": "success",
        "payment_id": str(payment["payment_id"]) if payment.get("payment_id") else None,
        "billing_attempt_id": str(attempt["billing_attempt_id"]) if attempt else None,
        "current_period_end": updated_subscription.get("current_period_end"),
    }


def _process_scheduled_downgrade(db: Session, plan_change, charge_client=None):
    billing_key = billing_service.get_active_billing_key_for_charge(
        db=db,
        user_id=plan_change["user_id"],
    )
    attempt_subscription = _plan_change_attempt_payload(plan_change)

    if not billing_key:
        attempt = _record_billing_attempt(
            db=db,
            subscription=attempt_subscription,
            plan_change_id=plan_change["plan_change_id"],
            attempt_type="scheduled_downgrade",
            status="failed",
            failure_code="billing_key_missing",
            failure_message="Active billing key was not found.",
        )
        _mark_plan_change_failed(
            db=db,
            plan_change_id=plan_change["plan_change_id"],
            status="failed",
        )
        return {
            "plan_change_id": str(plan_change["plan_change_id"]),
            "status": "failed",
            "billing_attempt_id": str(attempt["billing_attempt_id"]) if attempt else None,
            "failure_code": "billing_key_missing",
        }

    charge = _charge_subscription(
        subscription=attempt_subscription,
        billing_key=billing_key,
        charge_client=charge_client,
        order_suffix="scheduled downgrade",
    )
    if not charge.get("success"):
        attempt = _record_billing_attempt(
            db=db,
            subscription=attempt_subscription,
            billing_key_id=billing_key["billing_key_id"],
            plan_change_id=plan_change["plan_change_id"],
            attempt_type="scheduled_downgrade",
            status="failed",
            failure_code=charge.get("failure_code") or "billing_failed",
            failure_message=charge.get("failure_message"),
            pg_transaction_id=charge.get("pg_transaction_id"),
        )
        _mark_plan_change_failed(
            db=db,
            plan_change_id=plan_change["plan_change_id"],
            status="failed",
        )
        return {
            "plan_change_id": str(plan_change["plan_change_id"]),
            "status": "failed",
            "billing_attempt_id": str(attempt["billing_attempt_id"]) if attempt else None,
            "failure_code": charge.get("failure_code") or "billing_failed",
        }

    new_subscription = _insert_scheduled_downgrade_subscription(
        db=db,
        plan_change=plan_change,
        billing_key_id=billing_key["billing_key_id"],
    )
    payment = _insert_renewal_payment(
        db=db,
        subscription={
            **attempt_subscription,
            "subscription_id": new_subscription["subscription_id"],
        },
        billing_key_id=billing_key["billing_key_id"],
        charge=charge,
        plan_change_id=plan_change["plan_change_id"],
        order_suffix="scheduled downgrade",
    )
    db.execute(
        text("""
            UPDATE subscriptions
            SET
                last_payment_id = :payment_id,
                updated_at = NOW()
            WHERE subscription_id = :subscription_id
        """),
        {
            "payment_id": payment["payment_id"],
            "subscription_id": new_subscription["subscription_id"],
        },
    )
    attempt = _record_billing_attempt(
        db=db,
        subscription={
            **attempt_subscription,
            "subscription_id": new_subscription["subscription_id"],
        },
        billing_key_id=billing_key["billing_key_id"],
        payment_id=payment["payment_id"],
        plan_change_id=plan_change["plan_change_id"],
        attempt_type="scheduled_downgrade",
        status="success",
        pg_transaction_id=charge.get("pg_transaction_id"),
    )
    applied = db.execute(
        text("""
            UPDATE subscription_plan_changes
            SET
                status = 'applied',
                applied_at = NOW(),
                to_subscription_id = :to_subscription_id,
                updated_at = NOW()
            WHERE plan_change_id = :plan_change_id
              AND status = 'scheduled'
            RETURNING plan_change_id, status, applied_at, to_subscription_id
        """),
        {
            "plan_change_id": plan_change["plan_change_id"],
            "to_subscription_id": new_subscription["subscription_id"],
        },
    ).fetchone()
    db.execute(
        text("""
            UPDATE billing_keys
            SET
                last_used_at = NOW(),
                updated_at = NOW()
            WHERE billing_key_id = :billing_key_id
        """),
        {"billing_key_id": billing_key["billing_key_id"]},
    )

    applied_change = _row_mapping(applied)
    return {
        "plan_change_id": str(plan_change["plan_change_id"]),
        "status": applied_change["status"] if applied_change else "applied",
        "subscription_id": str(new_subscription["subscription_id"]),
        "payment_id": str(payment["payment_id"]) if payment.get("payment_id") else None,
        "billing_attempt_id": str(attempt["billing_attempt_id"]) if attempt else None,
    }


def _charge_subscription(subscription, billing_key, charge_client=None, order_suffix="renewal"):
    if charge_client:
        return charge_client(
            billing_key=billing_key["billing_key"],
            customer_key=billing_key.get("customer_key"),
            amount=int(subscription.get("price_amount") or 0),
            order_id=str(uuid.uuid4()),
            order_name=f"{subscription.get('plan_name') or subscription.get('plan_code')} {order_suffix}",
        )

    if os.getenv("TOSS_BILLING_TEST_MODE", "").lower() in ("1", "true", "yes"):
        return {
            "success": True,
            "pg_transaction_id": f"test-renewal-{uuid.uuid4()}",
            "method": "billing",
        }

    return {
        "success": False,
        "failure_code": "billing_client_not_configured",
        "failure_message": "Toss billing charge client is not configured.",
    }


def _insert_renewal_payment(
    db: Session,
    subscription,
    billing_key_id,
    charge,
    plan_change_id=None,
    order_suffix="renewal",
):
    row = db.execute(
        text("""
            INSERT INTO payments (
                user_id,
                subscription_id,
                product_type,
                plan_id,
                plan_change_id,
                billing_key_id,
                amount,
                status,
                pg_provider,
                pg_transaction_id,
                order_name,
                payment_method,
                toss_status,
                total_amount,
                balance_amount,
                currency,
                paid_at,
                approved_at,
                created_at,
                updated_at
            )
            VALUES (
                :user_id,
                :subscription_id,
                'subscription',
                :plan_id,
                :plan_change_id,
                :billing_key_id,
                :amount,
                'success',
                'toss',
                :pg_transaction_id,
                :order_name,
                :payment_method,
                'DONE',
                :amount,
                :amount,
                'KRW',
                NOW(),
                NOW(),
                NOW(),
                NOW()
            )
            RETURNING payment_id
        """),
        {
            "user_id": subscription["user_id"],
            "subscription_id": subscription["subscription_id"],
            "plan_id": subscription["plan_id"],
            "plan_change_id": plan_change_id,
            "billing_key_id": billing_key_id,
            "amount": int(subscription.get("price_amount") or 0),
            "pg_transaction_id": charge.get("pg_transaction_id"),
            "order_name": f"{subscription.get('plan_name') or subscription.get('plan_code')} {order_suffix}",
            "payment_method": charge.get("method") or "billing",
        },
    ).fetchone()
    return _row_mapping(row)


def _insert_scheduled_downgrade_subscription(db: Session, plan_change, billing_key_id):
    row = db.execute(
        text("""
            INSERT INTO subscriptions (
                user_id,
                plan_id,
                billing_key_id,
                status,
                started_at,
                ended_at,
                renew_at,
                current_period_start,
                current_period_end,
                next_billing_at,
                auto_renew,
                cancel_at_period_end,
                billing_status,
                created_at,
                updated_at
            )
            VALUES (
                :user_id,
                :plan_id,
                :billing_key_id,
                'active',
                NOW(),
                NOW() + INTERVAL '30 days',
                NOW() + INTERVAL '30 days',
                NOW(),
                NOW() + INTERVAL '30 days',
                NOW() + INTERVAL '30 days',
                true,
                false,
                'paid',
                NOW(),
                NOW()
            )
            RETURNING subscription_id, current_period_start, current_period_end, next_billing_at
        """),
        {
            "user_id": plan_change["user_id"],
            "plan_id": plan_change["to_plan_id"],
            "billing_key_id": billing_key_id,
        },
    ).fetchone()
    return _row_mapping(row)


def _extend_subscription_period(db: Session, subscription_id, payment_id):
    row = db.execute(
        text("""
            UPDATE subscriptions
            SET
                current_period_end = current_period_end + INTERVAL '30 days',
                ended_at = current_period_end + INTERVAL '30 days',
                renew_at = current_period_end + INTERVAL '30 days',
                next_billing_at = current_period_end + INTERVAL '30 days',
                billing_status = 'paid',
                last_payment_id = :payment_id,
                updated_at = NOW()
            WHERE subscription_id = :subscription_id
            RETURNING subscription_id, current_period_end, next_billing_at
        """),
        {
            "subscription_id": subscription_id,
            "payment_id": payment_id,
        },
    ).fetchone()
    return _row_mapping(row)


def _record_billing_attempt(
    db: Session,
    subscription,
    status,
    billing_key_id=None,
    payment_id=None,
    plan_change_id=None,
    attempt_type="renewal",
    failure_code=None,
    failure_message=None,
    pg_transaction_id=None,
):
    row = db.execute(
        text("""
            INSERT INTO subscription_billing_attempts (
                user_id,
                subscription_id,
                plan_change_id,
                payment_id,
                billing_key_id,
                attempt_type,
                status,
                attempt_no,
                amount,
                pg_provider,
                pg_transaction_id,
                failure_code,
                failure_message,
                attempted_at,
                created_at,
                updated_at
            )
            VALUES (
                :user_id,
                :subscription_id,
                :plan_change_id,
                :payment_id,
                :billing_key_id,
                :attempt_type,
                :status,
                COALESCE((
                    SELECT MAX(attempt_no) + 1
                    FROM subscription_billing_attempts
                    WHERE subscription_id = :subscription_id
                      AND attempt_type = :attempt_type
                ), 1),
                :amount,
                'toss',
                :pg_transaction_id,
                :failure_code,
                :failure_message,
                NOW(),
                NOW(),
                NOW()
            )
            RETURNING billing_attempt_id
        """),
        {
            "user_id": subscription["user_id"],
            "subscription_id": subscription["subscription_id"],
            "plan_change_id": plan_change_id,
            "payment_id": payment_id,
            "billing_key_id": billing_key_id,
            "attempt_type": attempt_type,
            "status": status,
            "amount": int(subscription.get("price_amount") or 0),
            "pg_transaction_id": pg_transaction_id,
            "failure_code": failure_code,
            "failure_message": failure_message,
        },
    ).fetchone()
    return _row_mapping(row)


def _plan_change_attempt_payload(plan_change):
    return {
        "subscription_id": plan_change.get("from_subscription_id") or plan_change.get("source_subscription_id"),
        "user_id": plan_change["user_id"],
        "plan_id": plan_change["to_plan_id"],
        "plan_code": plan_change.get("plan_code"),
        "plan_name": plan_change.get("plan_name"),
        "price_amount": plan_change.get("price_amount"),
        "credits": plan_change.get("credits"),
    }


def _mark_plan_change_failed(db: Session, plan_change_id, status="failed"):
    db.execute(
        text("""
            UPDATE subscription_plan_changes
            SET
                status = :status,
                updated_at = NOW()
            WHERE plan_change_id = :plan_change_id
              AND status = 'scheduled'
        """),
        {
            "plan_change_id": plan_change_id,
            "status": status,
        },
    )
