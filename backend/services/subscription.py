from sqlalchemy import text
from sqlalchemy.orm import Session


def _to_iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _row_mapping(row):
    if not row:
        return None
    return row._mapping if hasattr(row, "_mapping") else row


def award_pending_ai_refund(db: Session, user_id: str):
    # 1. Fetch pending AI refund
    row = db.execute(
        text("""
            SELECT pending_ai_refund_usage
            FROM user_credit_balances
            WHERE user_id = :user_id
        """),
        {"user_id": user_id}
    ).fetchone()
    
    if not row:
        return 0

    pending = int(row._mapping["pending_ai_refund_usage"])
    if pending <= 0:
        return 0

    # 10% refund (round half up or just integer division, let's use standard integer round)
    refund_amount = round(pending * 0.1)

    if refund_amount > 0:
        # 2. Add to free_balance and reset pending
        db.execute(
            text("""
                UPDATE user_credit_balances
                SET
                    free_balance = free_balance + :refund_amount,
                    pending_ai_refund_usage = 0,
                    updated_at = NOW()
                WHERE user_id = :user_id
            """),
            {"user_id": user_id, "refund_amount": refund_amount}
        )

        # 3. Log to credit_ledger
        db.execute(
            text("""
                INSERT INTO credit_ledger (
                    user_id, amount, balance_after, entry_type, source_type, source_id, description, created_at
                )
                VALUES (
                    :user_id, :refund_amount, 
                    (SELECT free_balance FROM user_credit_balances WHERE user_id = :user_id),
                    'ai_refund', 'system', 'ai_refund', 'AI 활용동의 리워드 10% 환급 (무료 크레딧)', NOW()
                )
            """),
            {"user_id": user_id, "refund_amount": refund_amount}
        )
    else:
        # Just reset
        db.execute(
            text("UPDATE user_credit_balances SET pending_ai_refund_usage = 0, updated_at = NOW() WHERE user_id = :user_id"),
            {"user_id": user_id}
        )

    return refund_amount


def _subscription_payload(row):
    if not row:
        return None
    return {
        "subscription_id": str(row["subscription_id"]) if row.get("subscription_id") else None,
        "status": row.get("subscription_status"),
        "current_period_start": _to_iso(row.get("current_period_start")),
        "current_period_end": _to_iso(row.get("current_period_end")),
        "next_billing_at": _to_iso(row.get("next_billing_at")),
        "auto_renew": row.get("auto_renew"),
        "cancel_at_period_end": row.get("cancel_at_period_end"),
        "cancelled_at": _to_iso(row.get("cancelled_at")),
        "billing_status": row.get("billing_status"),
        "carried_over_days": row.get("carried_over_days"),
        "superseded_by_subscription_id": (
            str(row["superseded_by_subscription_id"])
            if row.get("superseded_by_subscription_id")
            else None
        ),
    }


def _plan_payload(row):
    return {
        "plan_id": str(row["plan_id"]) if row.get("plan_id") else None,
        "plan_code": (row.get("plan_code") or "free").lower(),
        "plan_name": row.get("plan_name") or "Free",
        "plan_rank": int(row.get("plan_rank") or 0),
        "price_amount": int(row.get("price_amount") or 0),
        "credits": int(row.get("credits") or 0),
    }


def _default_free_plan():
    return {
        "plan_id": None,
        "plan_code": "free",
        "plan_name": "Free",
        "plan_rank": 0,
        "price_amount": 0,
        "credits": 0,
    }


def resolve_current_plan(db: Session, user_id: str):
    """현재 시점에 유효한 active 구독 중 plan_rank가 가장 높은 플랜을 반환한다."""
    current_row = db.execute(
        text("""
            SELECT
                s.subscription_id,
                s.status AS subscription_status,
                s.current_period_start,
                s.current_period_end,
                s.next_billing_at,
                s.auto_renew,
                s.cancel_at_period_end,
                s.cancelled_at,
                s.billing_status,
                s.carried_over_days,
                s.superseded_by_subscription_id,
                p.plan_id,
                p.plan_code,
                p.plan_name,
                p.plan_rank,
                p.price_amount,
                p.credits
            FROM subscriptions s
            JOIN plans p ON p.plan_id = s.plan_id
            WHERE s.user_id = :user_id
              AND s.status = 'active'
              AND s.current_period_start <= NOW()
              AND s.current_period_end > NOW()
            ORDER BY
                p.plan_rank DESC,
                s.current_period_end DESC,
                s.created_at DESC
            LIMIT 1
        """),
        {"user_id": user_id},
    ).fetchone()

    current = _row_mapping(current_row)
    if current:
        return {
            "current_plan": _plan_payload(current),
            "current_subscription": _subscription_payload(current),
            "is_fallback_free": False,
        }

    free_row = db.execute(
        text("""
            SELECT
                plan_id,
                plan_code,
                plan_name,
                plan_rank,
                price_amount,
                credits
            FROM plans
            WHERE LOWER(plan_code) = 'free'
              AND status = 'active'
            ORDER BY plan_rank ASC, sort_order ASC
            LIMIT 1
        """),
        {},
    ).fetchone()

    free = _row_mapping(free_row) or _default_free_plan()
    return {
        "current_plan": _plan_payload(free),
        "current_subscription": None,
        "is_fallback_free": True,
    }


def _get_target_plan(db: Session, to_plan_id: str):
    row = db.execute(
        text("""
            SELECT
                plan_id,
                plan_code,
                plan_name,
                plan_rank,
                price_amount,
                credits
            FROM plans
            WHERE status = 'active'
              AND (
                  CAST(plan_id AS varchar) = :to_plan_id
                  OR LOWER(plan_code) = LOWER(:to_plan_id)
              )
            LIMIT 1
        """),
        {"to_plan_id": to_plan_id},
    ).fetchone()

    target = _row_mapping(row)
    if not target:
        raise ValueError("대상 플랜을 찾을 수 없습니다.")
    return _plan_payload(target)


def classify_plan_change(db: Session, user_id: str, to_plan_id: str):
    """현재 플랜과 대상 플랜의 rank를 비교해 플랜 변경 유형만 판단한다."""
    current = resolve_current_plan(db, user_id)
    current_plan = current["current_plan"]
    target_plan = _get_target_plan(db, to_plan_id)

    current_rank = int(current_plan.get("plan_rank") or 0)
    target_rank = int(target_plan.get("plan_rank") or 0)
    target_code = (target_plan.get("plan_code") or "").lower()

    if target_code == "free":
        change_type = "cancel_to_free"
        apply_timing = "period_end"
        requires_payment_now = False
    elif target_rank > current_rank:
        change_type = "upgrade"
        apply_timing = "immediate"
        requires_payment_now = True
    elif target_rank < current_rank:
        change_type = "downgrade"
        apply_timing = "period_end"
        requires_payment_now = False
    else:
        change_type = "same_plan"
        apply_timing = "none"
        requires_payment_now = False

    return {
        "change_type": change_type,
        "apply_timing": apply_timing,
        "requires_payment_now": requires_payment_now,
        "current_plan": current_plan,
        "target_plan": target_plan,
        "current_subscription": current["current_subscription"],
    }


def request_plan_change(db: Session, user_id: str, to_plan_id: str):
    classification = classify_plan_change(db, user_id, to_plan_id)
    if classification["change_type"] == "cancel_to_free":
        scheduled = schedule_cancel_to_free(
            db=db,
            user_id=user_id,
            from_subscription_id=classification["current_subscription"]["subscription_id"],
            current_plan=classification["current_plan"],
            current_subscription=classification["current_subscription"],
            target_plan=classification["target_plan"],
        )
        return {
            **classification,
            "scheduled_plan_change": scheduled,
        }

    if classification["change_type"] != "downgrade":
        return classification

    scheduled = schedule_downgrade(
        db=db,
        user_id=user_id,
        from_subscription_id=classification["current_subscription"]["subscription_id"],
        to_plan_id=classification["target_plan"]["plan_id"],
        current_plan=classification["current_plan"],
        current_subscription=classification["current_subscription"],
        target_plan=classification["target_plan"],
    )

    return {
        **classification,
        "scheduled_plan_change": scheduled,
    }


def schedule_cancel_to_free(
    db: Session,
    user_id: str,
    from_subscription_id: str,
    current_plan=None,
    current_subscription=None,
    target_plan=None,
):
    if not current_plan or not current_subscription:
        current = resolve_current_plan(db, user_id)
        current_plan = current["current_plan"]
        current_subscription = current["current_subscription"]
    if not target_plan:
        target_plan = _get_target_plan(db, "free")

    if not current_subscription:
        raise ValueError("Active subscription was not found for cancellation.")

    effective_at = current_subscription["current_period_end"]
    if not effective_at:
        raise ValueError("Current subscription period end is required for cancellation scheduling.")

    db.execute(
        text("""
            UPDATE subscriptions
            SET
                auto_renew = false,
                cancel_at_period_end = true,
                cancelled_at = NOW(),
                status = 'active',
                updated_at = NOW()
            WHERE subscription_id = :subscription_id
        """),
        {"subscription_id": from_subscription_id},
    )

    db.execute(
        text("""
            UPDATE subscription_plan_changes
            SET
                status = 'cancelled',
                cancelled_at = NOW(),
                updated_at = NOW()
            WHERE user_id = :user_id
              AND from_subscription_id = :from_subscription_id
              AND change_type IN ('downgrade', 'cancel_to_free')
              AND status = 'scheduled'
        """),
        {
            "user_id": user_id,
            "from_subscription_id": from_subscription_id,
        },
    )

    row = db.execute(
        text("""
            INSERT INTO subscription_plan_changes (
                user_id,
                subscription_id,
                from_plan_id,
                to_plan_id,
                from_subscription_id,
                to_subscription_id,
                change_type,
                apply_timing,
                status,
                requested_at,
                effective_at,
                created_at,
                updated_at
            )
            VALUES (
                :user_id,
                :subscription_id,
                :from_plan_id,
                :to_plan_id,
                :from_subscription_id,
                NULL,
                'cancel_to_free',
                'period_end',
                'scheduled',
                NOW(),
                CAST(:effective_at AS timestamp),
                NOW(),
                NOW()
            )
            RETURNING plan_change_id, status, effective_at
        """),
        {
            "user_id": user_id,
            "subscription_id": from_subscription_id,
            "from_plan_id": current_plan["plan_id"],
            "to_plan_id": target_plan["plan_id"],
            "from_subscription_id": from_subscription_id,
            "effective_at": effective_at,
        },
    ).fetchone()
    scheduled = _row_mapping(row)

    return {
        "plan_change_id": str(scheduled["plan_change_id"]) if scheduled.get("plan_change_id") else None,
        "change_type": "cancel_to_free",
        "to_plan_id": target_plan["plan_id"],
        "to_plan_code": target_plan["plan_code"],
        "to_plan_name": target_plan["plan_name"],
        "status": scheduled["status"],
        "effective_at": _to_iso(scheduled["effective_at"]),
    }


def resume_subscription(db: Session, user_id: str, subscription_id: str):
    subscription_row = db.execute(
        text("""
            SELECT
                subscription_id,
                status,
                current_period_end,
                auto_renew,
                cancel_at_period_end
            FROM subscriptions
            WHERE subscription_id = :subscription_id
              AND user_id = :user_id
              AND status = 'active'
              AND cancel_at_period_end = true
              AND current_period_end > NOW()
            LIMIT 1
        """),
        {
            "subscription_id": subscription_id,
            "user_id": user_id,
        },
    ).fetchone()
    subscription = _row_mapping(subscription_row)
    if not subscription:
        raise ValueError("Resumable active subscription was not found.")

    updated_row = db.execute(
        text("""
            UPDATE subscriptions
            SET
                auto_renew = true,
                cancel_at_period_end = false,
                cancelled_at = NULL,
                updated_at = NOW()
            WHERE subscription_id = :subscription_id
            RETURNING
                subscription_id,
                status AS subscription_status,
                current_period_start,
                current_period_end,
                next_billing_at,
                auto_renew,
                cancel_at_period_end,
                cancelled_at,
                billing_status,
                carried_over_days,
                superseded_by_subscription_id
        """),
        {"subscription_id": subscription_id},
    ).fetchone()
    updated = _row_mapping(updated_row)

    db.execute(
        text("""
            UPDATE subscription_plan_changes
            SET
                status = 'cancelled',
                cancelled_at = NOW(),
                updated_at = NOW()
            WHERE user_id = :user_id
              AND from_subscription_id = :subscription_id
              AND change_type = 'cancel_to_free'
              AND status = 'scheduled'
        """),
        {
            "user_id": user_id,
            "subscription_id": subscription_id,
        },
    )

    return {
        "subscription_id": str(updated["subscription_id"]) if updated.get("subscription_id") else None,
        "status": "active",
        "auto_renew": updated.get("auto_renew"),
        "cancel_at_period_end": updated.get("cancel_at_period_end"),
        "cancelled_at": _to_iso(updated.get("cancelled_at")),
        "current_period_end": _to_iso(updated.get("current_period_end")),
    }


def cancel_scheduled_plan_change(db: Session, user_id: str, plan_change_id: str):
    plan_change_row = db.execute(
        text("""
            SELECT
                plan_change_id,
                change_type,
                status,
                from_subscription_id,
                effective_at
            FROM subscription_plan_changes
            WHERE plan_change_id = CAST(:plan_change_id AS uuid)
              AND user_id = :user_id
              AND status = 'scheduled'
            LIMIT 1
        """),
        {
            "plan_change_id": plan_change_id,
            "user_id": user_id,
        },
    ).fetchone()
    plan_change = _row_mapping(plan_change_row)
    if not plan_change:
        raise ValueError("Scheduled plan change was not found.")

    if plan_change.get("change_type") != "downgrade":
        raise ValueError("Only scheduled downgrades can be cancelled here.")

    updated_row = db.execute(
        text("""
            UPDATE subscription_plan_changes
            SET
                status = 'cancelled',
                cancelled_at = NOW(),
                updated_at = NOW()
            WHERE plan_change_id = CAST(:plan_change_id AS uuid)
            RETURNING plan_change_id, change_type, status, effective_at
        """),
        {"plan_change_id": plan_change_id},
    ).fetchone()
    updated = _row_mapping(updated_row)

    return {
        "plan_change_id": str(updated["plan_change_id"]) if updated.get("plan_change_id") else None,
        "change_type": updated.get("change_type"),
        "status": updated.get("status"),
        "effective_at": _to_iso(updated.get("effective_at")),
    }


def schedule_downgrade(
    db: Session,
    user_id: str,
    from_subscription_id: str,
    to_plan_id: str,
    current_plan=None,
    current_subscription=None,
    target_plan=None,
):
    if not current_plan or not current_subscription:
        current = resolve_current_plan(db, user_id)
        current_plan = current["current_plan"]
        current_subscription = current["current_subscription"]
    if not target_plan:
        target_plan = _get_target_plan(db, str(to_plan_id))

    if not current_subscription:
        raise ValueError("Active subscription was not found for downgrade.")

    if int(target_plan["plan_rank"]) >= int(current_plan.get("plan_rank") or 0):
        raise ValueError("Target plan must be lower than the current plan.")

    effective_at = current_subscription["current_period_end"]
    if not effective_at:
        raise ValueError("Current subscription period end is required for downgrade scheduling.")

    db.execute(
        text("""
            UPDATE subscription_plan_changes
            SET
                status = 'cancelled',
                cancelled_at = NOW(),
                updated_at = NOW()
            WHERE user_id = :user_id
              AND from_subscription_id = :from_subscription_id
              AND change_type = 'downgrade'
              AND status = 'scheduled'
        """),
        {
            "user_id": user_id,
            "from_subscription_id": from_subscription_id,
        },
    )

    row = db.execute(
        text("""
            INSERT INTO subscription_plan_changes (
                user_id,
                subscription_id,
                from_plan_id,
                to_plan_id,
                from_subscription_id,
                to_subscription_id,
                change_type,
                apply_timing,
                status,
                requested_at,
                effective_at,
                created_at,
                updated_at
            )
            VALUES (
                :user_id,
                :subscription_id,
                :from_plan_id,
                :to_plan_id,
                :from_subscription_id,
                NULL,
                'downgrade',
                'period_end',
                'scheduled',
                NOW(),
                CAST(:effective_at AS timestamp),
                NOW(),
                NOW()
            )
            RETURNING plan_change_id, status, effective_at
        """),
        {
            "user_id": user_id,
            "subscription_id": from_subscription_id,
            "from_plan_id": current_plan["plan_id"],
            "to_plan_id": target_plan["plan_id"],
            "from_subscription_id": from_subscription_id,
            "effective_at": effective_at,
        },
    ).fetchone()
    scheduled = _row_mapping(row)

    return {
        "plan_change_id": str(scheduled["plan_change_id"]) if scheduled.get("plan_change_id") else None,
        "change_type": "downgrade",
        "to_plan_id": target_plan["plan_id"],
        "to_plan_code": target_plan["plan_code"],
        "to_plan_name": target_plan["plan_name"],
        "status": scheduled["status"],
        "effective_at": _to_iso(scheduled["effective_at"]),
    }


def create_or_extend_subscription(
    db: Session,
    user_id: str,
    plan_id,
    payment_id=None,
):
    """결제 성공 후 같은 플랜 구독을 30일 생성하거나 연장한다."""
    existing_row = db.execute(
        text("""
            SELECT
                subscription_id,
                status,
                current_period_end
            FROM subscriptions
            WHERE user_id = :user_id
              AND plan_id = :plan_id
            ORDER BY
                CASE
                    WHEN status = 'active'
                     AND current_period_end IS NOT NULL
                     AND current_period_end > NOW()
                    THEN 0
                    ELSE 1
                END,
                current_period_end DESC NULLS LAST,
                updated_at DESC NULLS LAST,
                created_at DESC
            LIMIT 1
        """),
        {"user_id": user_id, "plan_id": plan_id},
    ).fetchone()

    existing = _row_mapping(existing_row)
    if existing and existing.get("status") == "active" and existing.get("current_period_end"):
        extend_row = db.execute(
            text("""
                UPDATE subscriptions
                SET
                    current_period_start = COALESCE(current_period_start, NOW()),
                    current_period_end = CASE
                        WHEN current_period_end > NOW()
                        THEN current_period_end + INTERVAL '30 days'
                        ELSE NOW() + INTERVAL '30 days'
                    END,
                    next_billing_at = CASE
                        WHEN current_period_end > NOW()
                        THEN current_period_end + INTERVAL '30 days'
                        ELSE NOW() + INTERVAL '30 days'
                    END,
                    ended_at = CASE
                        WHEN current_period_end > NOW()
                        THEN current_period_end + INTERVAL '30 days'
                        ELSE NOW() + INTERVAL '30 days'
                    END,
                    renew_at = CASE
                        WHEN current_period_end > NOW()
                        THEN current_period_end + INTERVAL '30 days'
                        ELSE NOW() + INTERVAL '30 days'
                    END,
                    status = 'active',
                    auto_renew = true,
                    cancel_at_period_end = false,
                    cancelled_at = NULL,
                    billing_status = 'paid',
                    last_payment_id = :payment_id,
                    updated_at = NOW()
                WHERE subscription_id = :subscription_id
                RETURNING subscription_id, current_period_start, current_period_end, next_billing_at
            """),
            {
                "subscription_id": existing["subscription_id"],
                "payment_id": payment_id,
            },
        ).fetchone()
        return _row_mapping(extend_row)

    if existing:
        reset_row = db.execute(
            text("""
                UPDATE subscriptions
                SET
                    status = 'active',
                    started_at = NOW(),
                    ended_at = NOW() + INTERVAL '30 days',
                    renew_at = NOW() + INTERVAL '30 days',
                    current_period_start = NOW(),
                    current_period_end = NOW() + INTERVAL '30 days',
                    next_billing_at = NOW() + INTERVAL '30 days',
                    auto_renew = true,
                    cancel_at_period_end = false,
                    cancelled_at = NULL,
                    billing_status = 'paid',
                    last_payment_id = :payment_id,
                    upgraded_at = NULL,
                    superseded_by_subscription_id = NULL,
                    carried_over_days = 0,
                    original_period_end = NULL,
                    updated_at = NOW()
                WHERE subscription_id = :subscription_id
                RETURNING subscription_id, current_period_start, current_period_end, next_billing_at
            """),
            {
                "subscription_id": existing["subscription_id"],
                "payment_id": payment_id,
            },
        ).fetchone()
        return _row_mapping(reset_row)

    insert_row = db.execute(
        text("""
            INSERT INTO subscriptions (
                user_id,
                plan_id,
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
                last_payment_id,
                created_at,
                updated_at
            )
            VALUES (
                :user_id,
                :plan_id,
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
                :payment_id,
                NOW(),
                NOW()
            )
            RETURNING subscription_id, current_period_start, current_period_end, next_billing_at
        """),
        {
            "user_id": user_id,
            "plan_id": plan_id,
            "payment_id": payment_id,
        },
    ).fetchone()
    return _row_mapping(insert_row)


def apply_upgrade_with_carryover(
    db: Session,
    user_id: str,
    from_subscription_id=None,
    to_plan_id=None,
    payment_id=None,
):
    """Create the upgraded subscription now and carry the lower plan's remaining time after it."""
    if not to_plan_id:
        raise ValueError("Target plan is required for upgrade.")

    target_plan = _get_target_plan(db, str(to_plan_id))
    lower = _find_upgrade_source_subscription(
        db=db,
        user_id=user_id,
        from_subscription_id=from_subscription_id,
    )
    if not lower:
        raise ValueError("Active source subscription was not found for upgrade.")

    if int(target_plan["plan_rank"]) <= int(lower.get("plan_rank") or 0):
        raise ValueError("Target plan must be higher than the current plan.")

    upper_row = db.execute(
        text("""
            INSERT INTO subscriptions (
                user_id,
                plan_id,
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
                last_payment_id,
                created_at,
                updated_at
            )
            VALUES (
                :user_id,
                :plan_id,
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
                :payment_id,
                NOW(),
                NOW()
            )
            RETURNING subscription_id, current_period_start, current_period_end, next_billing_at
        """),
        {
            "user_id": user_id,
            "plan_id": target_plan["plan_id"],
            "payment_id": payment_id,
        },
    ).fetchone()
    upper = _row_mapping(upper_row)

    lower_update_row = db.execute(
        text("""
            WITH remaining AS (
                SELECT
                    current_period_end AS original_end,
                    GREATEST(0, EXTRACT(EPOCH FROM (current_period_end - NOW()))) AS remaining_seconds,
                    CEIL(GREATEST(0, EXTRACT(EPOCH FROM (current_period_end - NOW()))) / 86400.0)::integer AS remaining_days
                FROM subscriptions
                WHERE subscription_id = :lower_subscription_id
            ),
            calculated AS (
                SELECT
                    original_end,
                    remaining_seconds,
                    remaining_days,
                    CAST(:upper_period_end AS timestamp)
                        + (remaining_seconds || ' seconds')::interval AS carried_end
                FROM remaining
            )
            UPDATE subscriptions s
            SET
                original_period_end = COALESCE(s.original_period_end, calculated.original_end),
                current_period_end = calculated.carried_end,
                ended_at = calculated.carried_end,
                renew_at = calculated.carried_end,
                next_billing_at = NULL,
                auto_renew = false,
                cancel_at_period_end = true,
                billing_status = 'paid',
                upgraded_at = NOW(),
                superseded_by_subscription_id = :upper_subscription_id,
                carried_over_days = calculated.remaining_days,
                updated_at = NOW()
            FROM calculated
            WHERE s.subscription_id = :lower_subscription_id
            RETURNING
                s.subscription_id,
                s.plan_id,
                s.original_period_end,
                s.current_period_end,
                s.carried_over_days,
                calculated.remaining_seconds
        """),
        {
            "lower_subscription_id": lower["subscription_id"],
            "upper_subscription_id": upper["subscription_id"],
            "upper_period_end": upper["current_period_end"],
        },
    ).fetchone()
    lower_update = _row_mapping(lower_update_row)

    plan_change_row = db.execute(
        text("""
            INSERT INTO subscription_plan_changes (
                user_id,
                subscription_id,
                from_plan_id,
                to_plan_id,
                from_subscription_id,
                to_subscription_id,
                change_type,
                apply_timing,
                status,
                remaining_days,
                remaining_seconds,
                from_subscription_original_end,
                from_subscription_new_end,
                requested_at,
                effective_at,
                applied_at,
                created_at,
                updated_at
            )
            VALUES (
                :user_id,
                :upper_subscription_id,
                :from_plan_id,
                :to_plan_id,
                :lower_subscription_id,
                :upper_subscription_id,
                'upgrade',
                'immediate',
                'applied',
                :remaining_days,
                :remaining_seconds,
                :original_period_end,
                :current_period_end,
                NOW(),
                NOW(),
                NOW(),
                NOW(),
                NOW()
            )
            RETURNING plan_change_id
        """),
        {
            "user_id": user_id,
            "upper_subscription_id": upper["subscription_id"],
            "from_plan_id": lower["plan_id"],
            "to_plan_id": target_plan["plan_id"],
            "lower_subscription_id": lower["subscription_id"],
            "remaining_days": lower_update["carried_over_days"],
            "remaining_seconds": lower_update["remaining_seconds"],
            "original_period_end": lower_update["original_period_end"],
            "current_period_end": lower_update["current_period_end"],
        },
    ).fetchone()
    plan_change = _row_mapping(plan_change_row)

    return {
        "subscription_id": upper["subscription_id"],
        "upper_subscription": upper,
        "lower_subscription": lower_update,
        "plan_change_id": plan_change["plan_change_id"] if plan_change else None,
        "carried_over_days": lower_update["carried_over_days"],
    }


def _find_upgrade_source_subscription(
    db: Session,
    user_id: str,
    from_subscription_id=None,
):
    params = {
        "user_id": user_id,
        "from_subscription_id": from_subscription_id,
    }
    id_filter = (
        "AND s.subscription_id = :from_subscription_id"
        if from_subscription_id
        else ""
    )
    row = db.execute(
        text(f"""
            SELECT
                s.subscription_id,
                s.plan_id,
                s.current_period_start,
                s.current_period_end,
                p.plan_rank
            FROM subscriptions s
            JOIN plans p ON p.plan_id = s.plan_id
            WHERE s.user_id = :user_id
              AND s.status = 'active'
              AND s.current_period_start <= NOW()
              AND s.current_period_end > NOW()
              {id_filter}
            ORDER BY
                p.plan_rank DESC,
                s.current_period_end DESC,
                s.created_at DESC
            LIMIT 1
        """),
        params,
    ).fetchone()

    lower = _row_mapping(row)
    if lower or not from_subscription_id:
        return lower

    return _find_upgrade_source_subscription(
        db=db,
        user_id=user_id,
        from_subscription_id=None,
    )
