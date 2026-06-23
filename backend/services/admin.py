import json

from sqlalchemy import text
from utils.database import SessionLocal


DEFAULT_ADMIN_POLICIES = {
    "file_processing": {
        "plans": {
            "free":   {"fileSizeLimit": 50,   "maxJobs": 3,  "monthlyQuota": 5,    "resultRetention": 3,  "watermarkRequired": True},
            "pro":    {"fileSizeLimit": 500,  "maxJobs": 10, "monthlyQuota": 50,   "resultRetention": 7,  "watermarkRequired": False},
            "studio": {"fileSizeLimit": 2048, "maxJobs": 30, "monthlyQuota": None, "resultRetention": 30, "watermarkRequired": False},
        },
        "allowedFormats": ["jpg", "jpeg", "png", "webp", "mp4", "mov"],
    },
    "payment": {
        "plans": {
            "free":   {"credits": 5,   "price": 0},
            "pro":    {"credits": 50,  "price": 2900},
            "studio": {"credits": 500, "price": 19800},
        },
        "creditPlans": {
            "credit_100": {"credits": 100, "bonusCredits": 0, "price": 5000},
            "credit_500": {"credits": 500, "bonusCredits": 0, "price": 20000},
        },
    },
    "retention": {
        "plans": {
            "free":   {"autoDeleteOriginalHours": 12, "metadataRetentionDays": 90},
            "pro":    {"autoDeleteOriginalHours": 12, "metadataRetentionDays": 90},
            "studio": {"autoDeleteOriginalHours": 12, "metadataRetentionDays": 90},
        },
    },
    "notification": {
        "notifyAbuse": True,
        "queueDelayMinutes": 30,
        "autoReport": True,
    },
}


PLAN_FIELDS = {
    "plan_code",
    "plan_name",
    "badge_label",
    "badge_class",
    "description",
    "monthly_quota",
    "result_retention_days",
    "watermark_required",
    "price_amount",
    "sort_order",
    "status",
    "file_size_limit",
    "max_jobs",
    "auto_delete_original_hours",
    "metadata_retention_days",
    "credits",
}

CREDIT_PLAN_FIELDS = {
    "credit_plan_code",
    "credit_plan_name",
    "price_amount",
    "base_credits",
    "bonus_credits",
    "expires_days",
    "sort_order",
    "status",
}

VALID_MANAGEMENT_STATUSES = {"active", "inactive", "deleted"}
PLAN_PAGE_LIMITS = {5, 10, 20, 50, 100}


def _row_to_dict(row):
    data = {}
    for key, value in row._mapping.items():
        if hasattr(value, "isoformat"):
            data[key] = value.isoformat()
        else:
            data[key] = str(value) if key.endswith("_id") and value is not None else value
    return data


def _clean_payload(payload: dict, allowed_fields: set[str]):
    cleaned = {key: value for key, value in payload.items() if key in allowed_fields}
    if "status" in cleaned and cleaned["status"] not in VALID_MANAGEMENT_STATUSES:
        raise ValueError("status must be one of active, inactive, deleted")
    return cleaned


def _build_filter_clause(code_column: str, name_column: str, q=None, include_deleted=False, status=None):
    conditions = []
    params = {}

    if status:
        conditions.append("status = :status_filter")
        params["status_filter"] = status
    elif not include_deleted:
        conditions.append("status <> 'deleted'")
    if q:
        conditions.append(
            f"(LOWER({code_column}) LIKE :q OR LOWER({name_column}) LIKE :q OR LOWER(status) LIKE :q)"
        )
        params["q"] = f"%{q.lower()}%"

    return ("WHERE " + " AND ".join(conditions)) if conditions else "", params


def _normalize_page_params(page: int = 1, limit: int = 20):
    page = max(int(page or 1), 1)
    limit = int(limit or 20)
    if limit not in PLAN_PAGE_LIMITS:
        limit = 20
    return page, limit, (page - 1) * limit


def _parse_bool_filter(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise ValueError("boolean filter must be true or false")


def list_subscription_plans(
    q=None,
    include_deleted: bool = False,
    status: str = None,
    page: int = 1,
    limit: int = 20,
):
    db = SessionLocal()
    try:
        if status and status not in VALID_MANAGEMENT_STATUSES:
            raise ValueError("status must be one of active, inactive, deleted")
        page, limit, offset = _normalize_page_params(page, limit)
        where, params = _build_filter_clause("plan_code", "plan_name", q, include_deleted, status)
        total = db.execute(
            text(f"""
                SELECT COUNT(*)
                FROM plans
                {where}
            """),
            params,
        ).scalar()
        rows = db.execute(
            text(f"""
                SELECT
                    plan_id,
                    plan_code,
                    plan_name,
                    badge_label,
                    badge_class,
                    description,
                    monthly_quota,
                    result_retention_days,
                    watermark_required,
                    price_amount,
                    sort_order,
                    status,
                    file_size_limit,
                    max_jobs,
                    auto_delete_original_hours,
                    metadata_retention_days,
                    credits,
                    created_at,
                    updated_at
                FROM plans
                {where}
                ORDER BY sort_order ASC, created_at ASC
                LIMIT :limit OFFSET :offset
            """),
            {**params, "limit": limit, "offset": offset},
        ).fetchall()
        return {
            "data": [_row_to_dict(row) for row in rows],
            "total": total or 0,
            "page": page,
            "limit": limit,
        }
    finally:
        db.close()


def create_subscription_plan(payload: dict):
    data = _clean_payload(payload, PLAN_FIELDS)
    required = {"plan_code", "plan_name", "result_retention_days"}
    missing = [field for field in required if data.get(field) in (None, "")]
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")

    db = SessionLocal()
    try:
        if data.get("status") == "active":
            active_count = db.execute(
                text("SELECT COUNT(*) FROM plans WHERE status = 'active'")
            ).scalar()
            if active_count >= 4:
                raise ValueError("활성화된 구독 플랜 카드는 최대 4개까지만 등록할 수 있습니다.")

        columns = list(data.keys())
        placeholders = [f":{column}" for column in columns]
        row = db.execute(
            text(f"""
                INSERT INTO plans ({", ".join(columns)})
                VALUES ({", ".join(placeholders)})
                RETURNING
                    plan_id,
                    plan_code,
                    plan_name,
                    badge_label,
                    badge_class,
                    description,
                    monthly_quota,
                    result_retention_days,
                    watermark_required,
                    price_amount,
                    sort_order,
                    status,
                    file_size_limit,
                    max_jobs,
                    auto_delete_original_hours,
                    metadata_retention_days,
                    credits,
                    created_at,
                    updated_at
            """),
            data,
        ).fetchone()
        db.commit()
        return _row_to_dict(row)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def update_subscription_plan(plan_id: str, payload: dict):
    data = _clean_payload(payload, PLAN_FIELDS)
    if not data:
        raise ValueError("no updatable fields provided")

    db = SessionLocal()
    try:
        if data.get("status") == "active":
            active_count = db.execute(
                text("SELECT COUNT(*) FROM plans WHERE status = 'active' AND plan_id <> CAST(:plan_id AS uuid)"),
                {"plan_id": plan_id}
            ).scalar()
            if active_count >= 4:
                raise ValueError("활성화된 구독 플랜 카드는 최대 4개까지만 등록할 수 있습니다.")

        set_clause = ", ".join([f"{field} = :{field}" for field in data])
        params = {**data, "plan_id": plan_id}
        row = db.execute(
            text(f"""
                UPDATE plans
                SET {set_clause},
                    updated_at = NOW()
                WHERE plan_id = CAST(:plan_id AS uuid)
                RETURNING
                    plan_id,
                    plan_code,
                    plan_name,
                    badge_label,
                    badge_class,
                    description,
                    monthly_quota,
                    result_retention_days,
                    watermark_required,
                    price_amount,
                    sort_order,
                    status,
                    file_size_limit,
                    max_jobs,
                    auto_delete_original_hours,
                    metadata_retention_days,
                    credits,
                    created_at,
                    updated_at
            """),
            params,
        ).fetchone()
        if not row:
            raise ValueError("subscription plan not found")
        db.commit()
        return _row_to_dict(row)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def delete_subscription_plan(plan_id: str):
    return update_subscription_plan(plan_id, {"status": "deleted"})


def list_credit_plans(
    q=None,
    include_deleted: bool = False,
    status: str = None,
    page: int = 1,
    limit: int = 20,
):
    db = SessionLocal()
    try:
        if status and status not in VALID_MANAGEMENT_STATUSES:
            raise ValueError("status must be one of active, inactive, deleted")
        page, limit, offset = _normalize_page_params(page, limit)
        where, params = _build_filter_clause(
            "credit_plan_code", "credit_plan_name", q, include_deleted, status
        )
        total = db.execute(
            text(f"""
                SELECT COUNT(*)
                FROM credit_plans
                {where}
            """),
            params,
        ).scalar()
        rows = db.execute(
            text(f"""
                SELECT
                    credit_plan_id,
                    credit_plan_code,
                    credit_plan_name,
                    price_amount,
                    base_credits,
                    bonus_credits,
                    expires_days,
                    sort_order,
                    status,
                    created_at,
                    updated_at
                FROM credit_plans
                {where}
                ORDER BY sort_order ASC, created_at ASC
                LIMIT :limit OFFSET :offset
            """),
            {**params, "limit": limit, "offset": offset},
        ).fetchall()
        return {
            "data": [_row_to_dict(row) for row in rows],
            "total": total or 0,
            "page": page,
            "limit": limit,
        }
    finally:
        db.close()


def create_credit_plan(payload: dict):
    data = _clean_payload(payload, CREDIT_PLAN_FIELDS)
    required = {"credit_plan_code", "credit_plan_name", "price_amount", "base_credits"}
    missing = [field for field in required if data.get(field) in (None, "")]
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")

    db = SessionLocal()
    try:
        if data.get("status") == "active":
            active_count = db.execute(
                text("SELECT COUNT(*) FROM credit_plans WHERE status = 'active'")
            ).scalar()
            if active_count >= 8:
                raise ValueError("활성화된 크레딧 플랜 카드는 최대 8개까지만 등록할 수 있습니다.")

        columns = list(data.keys())
        placeholders = [f":{column}" for column in columns]
        row = db.execute(
            text(f"""
                INSERT INTO credit_plans ({", ".join(columns)})
                VALUES ({", ".join(placeholders)})
                RETURNING
                    credit_plan_id,
                    credit_plan_code,
                    credit_plan_name,
                    price_amount,
                    base_credits,
                    bonus_credits,
                    expires_days,
                    sort_order,
                    status,
                    created_at,
                    updated_at
            """),
            data,
        ).fetchone()
        db.commit()
        return _row_to_dict(row)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def update_credit_plan(credit_plan_id: str, payload: dict):
    data = _clean_payload(payload, CREDIT_PLAN_FIELDS)
    if not data:
        raise ValueError("no updatable fields provided")

    db = SessionLocal()
    try:
        if data.get("status") == "active":
            active_count = db.execute(
                text("SELECT COUNT(*) FROM credit_plans WHERE status = 'active' AND credit_plan_id <> CAST(:credit_plan_id AS uuid)"),
                {"credit_plan_id": credit_plan_id}
            ).scalar()
            if active_count >= 8:
                raise ValueError("활성화된 크레딧 플랜 카드는 최대 8개까지만 등록할 수 있습니다.")

        set_clause = ", ".join([f"{field} = :{field}" for field in data])
        params = {**data, "credit_plan_id": credit_plan_id}
        row = db.execute(
            text(f"""
                UPDATE credit_plans
                SET {set_clause},
                    updated_at = NOW()
                WHERE credit_plan_id = CAST(:credit_plan_id AS uuid)
                RETURNING
                    credit_plan_id,
                    credit_plan_code,
                    credit_plan_name,
                    price_amount,
                    base_credits,
                    bonus_credits,
                    expires_days,
                    sort_order,
                    status,
                    created_at,
                    updated_at
            """),
            params,
        ).fetchone()
        if not row:
            raise ValueError("credit plan not found")
        db.commit()
        return _row_to_dict(row)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def delete_credit_plan(credit_plan_id: str):
    return update_credit_plan(credit_plan_id, {"status": "deleted"})


def get_admin_subscriptions_list(
    q=None,
    search_key="email",
    plan_code=None,
    subscription_status=None,
    auto_renew=None,
    cancel_scheduled=None,
    billing_failed=None,
    scheduled_change=None,
    page=1,
    limit=10,
):
    page, limit, offset = _normalize_page_params(page, limit)
    auto_renew = _parse_bool_filter(auto_renew)
    cancel_scheduled = _parse_bool_filter(cancel_scheduled)
    billing_failed = _parse_bool_filter(billing_failed)
    scheduled_change = _parse_bool_filter(scheduled_change)

    conditions = []
    params = {}

    if q:
        params["q"] = f"%{q.lower()}%"
        if search_key == "user_id":
            conditions.append("LOWER(CAST(u.user_id AS text)) LIKE :q")
        elif search_key == "all":
            conditions.append("(LOWER(u.email) LIKE :q OR LOWER(CAST(u.user_id AS text)) LIKE :q)")
        else:
            conditions.append("LOWER(u.email) LIKE :q")

    if plan_code:
        conditions.append("COALESCE(current_plan.plan_code, free_plan.plan_code) = :plan_code")
        params["plan_code"] = plan_code

    if subscription_status:
        if subscription_status == "free":
            conditions.append("current_sub.subscription_id IS NULL")
        else:
            conditions.append("COALESCE(current_sub.status, 'free') = :subscription_status")
            params["subscription_status"] = subscription_status

    if auto_renew is not None:
        if auto_renew:
            conditions.append("current_sub.auto_renew IS TRUE")
        else:
            conditions.append("(current_sub.subscription_id IS NULL OR current_sub.auto_renew IS FALSE)")

    if cancel_scheduled is not None:
        if cancel_scheduled:
            conditions.append("current_sub.cancel_at_period_end IS TRUE")
        else:
            conditions.append("(current_sub.subscription_id IS NULL OR current_sub.cancel_at_period_end IS FALSE)")

    if billing_failed is not None:
        if billing_failed:
            conditions.append("COALESCE(current_sub.billing_status, '') IN ('failed', 'billing_key_missing')")
        else:
            conditions.append("COALESCE(current_sub.billing_status, '') NOT IN ('failed', 'billing_key_missing')")

    if scheduled_change is not None:
        if scheduled_change:
            conditions.append("scheduled_change.plan_change_id IS NOT NULL")
        else:
            conditions.append("scheduled_change.plan_change_id IS NULL")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    base_from = f"""
        FROM users u
        LEFT JOIN LATERAL (
            SELECT
                s.subscription_id,
                s.plan_id,
                s.status,
                s.current_period_start,
                s.current_period_end,
                s.next_billing_at,
                s.auto_renew,
                s.cancel_at_period_end,
                s.cancelled_at,
                s.billing_status,
                s.carried_over_days,
                s.superseded_by_subscription_id,
                s.original_period_end,
                s.upgraded_at,
                p.plan_code,
                p.plan_name,
                p.plan_rank
            FROM subscriptions s
            JOIN plans p ON p.plan_id = s.plan_id
            WHERE s.user_id = u.user_id
              AND s.status = 'active'
              AND (
                  s.current_period_end IS NULL
                  OR s.current_period_end > NOW()
              )
            ORDER BY p.plan_rank DESC, s.current_period_end DESC NULLS LAST, s.created_at DESC
            LIMIT 1
        ) current_sub ON TRUE
        LEFT JOIN plans current_plan ON current_plan.plan_id = current_sub.plan_id
        LEFT JOIN plans free_plan ON free_plan.plan_code = 'free' AND free_plan.status = 'active'
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) AS active_subscription_count
            FROM subscriptions s
            WHERE s.user_id = u.user_id
              AND s.status = 'active'
              AND (
                  s.current_period_end IS NULL
                  OR s.current_period_end > NOW()
              )
        ) active_counts ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                pc.plan_change_id,
                pc.change_type,
                pc.status,
                pc.effective_at,
                pc.created_at,
                tp.plan_code AS to_plan_code,
                tp.plan_name AS to_plan_name
            FROM subscription_plan_changes pc
            LEFT JOIN plans tp ON tp.plan_id = pc.to_plan_id
            WHERE pc.user_id = u.user_id
              AND pc.status = 'scheduled'
            ORDER BY pc.created_at DESC
            LIMIT 1
        ) scheduled_change ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                s.subscription_id,
                p.plan_code,
                p.plan_name,
                s.current_period_end,
                s.carried_over_days,
                s.superseded_by_subscription_id
            FROM subscriptions s
            JOIN plans p ON p.plan_id = s.plan_id
            WHERE s.user_id = u.user_id
              AND current_sub.subscription_id IS NOT NULL
              AND s.superseded_by_subscription_id = current_sub.subscription_id
            ORDER BY s.current_period_end DESC NULLS LAST, s.created_at DESC
            LIMIT 1
        ) carried_over ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                attempted_at,
                status,
                attempt_type,
                failure_message
            FROM subscription_billing_attempts sba
            WHERE sba.user_id = u.user_id
            ORDER BY attempted_at DESC, created_at DESC
            LIMIT 1
        ) last_attempt ON TRUE
        {where_clause}
    """

    db = SessionLocal()
    try:
        total = db.execute(text(f"SELECT COUNT(*) {base_from}"), params).scalar() or 0

        list_query = f"""
            SELECT
                u.user_id,
                u.email,
                COALESCE(current_plan.plan_code, free_plan.plan_code, 'free') AS current_plan_code,
                COALESCE(current_plan.plan_name, free_plan.plan_name, 'Free') AS current_plan_name,
                current_sub.subscription_id,
                current_sub.status AS subscription_status,
                current_sub.current_period_start,
                current_sub.current_period_end,
                current_sub.next_billing_at,
                current_sub.auto_renew,
                current_sub.cancel_at_period_end,
                current_sub.cancelled_at,
                current_sub.billing_status,
                COALESCE(active_counts.active_subscription_count, 0) AS active_subscription_count,
                carried_over.subscription_id AS carried_over_subscription_id,
                carried_over.plan_code AS carried_over_plan_code,
                carried_over.plan_name AS carried_over_plan_name,
                carried_over.current_period_end AS carried_over_period_end,
                carried_over.carried_over_days,
                scheduled_change.plan_change_id,
                scheduled_change.change_type AS scheduled_change_type,
                scheduled_change.status AS scheduled_change_status,
                scheduled_change.effective_at AS scheduled_change_effective_at,
                scheduled_change.to_plan_code AS scheduled_to_plan_code,
                scheduled_change.to_plan_name AS scheduled_to_plan_name,
                last_attempt.attempted_at AS last_attempted_at,
                last_attempt.status AS last_attempt_status,
                last_attempt.attempt_type AS last_attempt_type,
                last_attempt.failure_message AS last_failure_reason
            {base_from}
            ORDER BY
                CASE
                    WHEN COALESCE(current_sub.billing_status, '') IN ('failed', 'billing_key_missing') THEN 0
                    ELSE 1
                END,
                u.created_at DESC,
                u.user_id DESC
            LIMIT :limit OFFSET :offset
        """
        rows = db.execute(text(list_query), {**params, "limit": limit, "offset": offset}).fetchall()

        summary_query = """
            SELECT
                COUNT(*) AS total_users,
                COUNT(*) FILTER (WHERE current_sub.subscription_id IS NOT NULL) AS paid_users,
                COUNT(*) FILTER (WHERE COALESCE(current_sub.billing_status, '') IN ('failed', 'billing_key_missing')) AS billing_failed_users,
                COUNT(*) FILTER (WHERE scheduled_change.plan_change_id IS NOT NULL) AS scheduled_change_users
            """ + base_from
        summary_row = db.execute(text(summary_query), params).fetchone()
        summary_map = summary_row._mapping if summary_row else {}

        data = []
        for row in rows:
            m = row._mapping
            data.append({
                "user_id": str(m["user_id"]),
                "email": m["email"] or "",
                "current_plan_code": m["current_plan_code"] or "free",
                "current_plan_name": m["current_plan_name"] or "Free",
                "current_subscription": {
                    "subscription_id": str(m["subscription_id"]) if m["subscription_id"] else None,
                    "status": m["subscription_status"] or "free",
                    "current_period_start": m["current_period_start"].isoformat() if m["current_period_start"] else None,
                    "current_period_end": m["current_period_end"].isoformat() if m["current_period_end"] else None,
                    "next_billing_at": m["next_billing_at"].isoformat() if m["next_billing_at"] else None,
                    "auto_renew": bool(m["auto_renew"]) if m["subscription_id"] else False,
                    "cancel_at_period_end": bool(m["cancel_at_period_end"]) if m["subscription_id"] else False,
                    "cancelled_at": m["cancelled_at"].isoformat() if m["cancelled_at"] else None,
                    "billing_status": m["billing_status"] or None,
                },
                "active_subscription_count": int(m["active_subscription_count"] or 0),
                "carried_over_subscription": {
                    "subscription_id": str(m["carried_over_subscription_id"]) if m["carried_over_subscription_id"] else None,
                    "plan_code": m["carried_over_plan_code"],
                    "plan_name": m["carried_over_plan_name"],
                    "current_period_end": m["carried_over_period_end"].isoformat() if m["carried_over_period_end"] else None,
                    "carried_over_days": int(m["carried_over_days"] or 0),
                } if m["carried_over_subscription_id"] else None,
                "scheduled_plan_change": {
                    "plan_change_id": str(m["plan_change_id"]) if m["plan_change_id"] else None,
                    "change_type": m["scheduled_change_type"],
                    "status": m["scheduled_change_status"],
                    "effective_at": m["scheduled_change_effective_at"].isoformat() if m["scheduled_change_effective_at"] else None,
                    "to_plan_code": m["scheduled_to_plan_code"],
                    "to_plan_name": m["scheduled_to_plan_name"],
                } if m["plan_change_id"] else None,
                "latest_billing_attempt": {
                    "attempted_at": m["last_attempted_at"].isoformat() if m["last_attempted_at"] else None,
                    "status": m["last_attempt_status"],
                    "attempt_type": m["last_attempt_type"],
                    "failure_reason": m["last_failure_reason"],
                } if m["last_attempted_at"] else None,
            })

        return {
            "data": data,
            "summary": {
                "total_users": int(summary_map.get("total_users") or 0),
                "paid_users": int(summary_map.get("paid_users") or 0),
                "billing_failed_users": int(summary_map.get("billing_failed_users") or 0),
                "scheduled_change_users": int(summary_map.get("scheduled_change_users") or 0),
            },
            "total": total,
            "page": page,
            "limit": limit,
        }
    finally:
        db.close()


def get_admin_subscription_detail(user_id: str):
    db = SessionLocal()
    try:
        current_query = """
            SELECT
                u.user_id,
                u.email,
                cs.subscription_id,
                cs.status AS subscription_status,
                cs.current_period_start,
                cs.current_period_end,
                cs.next_billing_at,
                cs.auto_renew,
                cs.cancel_at_period_end,
                cs.cancelled_at,
                cs.billing_status,
                cs.carried_over_days,
                cs.superseded_by_subscription_id,
                cp.plan_code AS current_plan_code,
                cp.plan_name AS current_plan_name,
                fp.plan_code AS free_plan_code,
                fp.plan_name AS free_plan_name
            FROM users u
            LEFT JOIN LATERAL (
                SELECT s.*
                FROM subscriptions s
                JOIN plans p ON p.plan_id = s.plan_id
                WHERE s.user_id = u.user_id
                  AND s.status = 'active'
                  AND (
                      s.current_period_end IS NULL
                      OR s.current_period_end > NOW()
                  )
                ORDER BY p.plan_rank DESC, s.current_period_end DESC NULLS LAST, s.created_at DESC
                LIMIT 1
            ) cs ON TRUE
            LEFT JOIN plans cp ON cp.plan_id = cs.plan_id
            LEFT JOIN plans fp ON fp.plan_code = 'free' AND fp.status = 'active'
            WHERE u.user_id = CAST(:user_id AS uuid)
        """
        current_row = db.execute(text(current_query), {"user_id": user_id}).fetchone()
        if not current_row:
            raise ValueError("user not found")

        current = current_row._mapping

        active_query = """
            SELECT
                s.subscription_id,
                s.status,
                s.current_period_start,
                s.current_period_end,
                s.next_billing_at,
                s.auto_renew,
                s.cancel_at_period_end,
                s.cancelled_at,
                s.billing_status,
                s.carried_over_days,
                s.superseded_by_subscription_id,
                s.original_period_end,
                s.upgraded_at,
                s.created_at,
                p.plan_id,
                p.plan_code,
                p.plan_name,
                p.credits AS plan_credits,
                -- 해당 구독의 가장 최근 결제 시각 (경고: 14일 경과 체크용)
                (
                    SELECT py.paid_at FROM payments py
                    WHERE py.subscription_id = s.subscription_id
                      AND py.status = 'success'
                    ORDER BY py.paid_at DESC NULLS LAST
                    LIMIT 1
                ) AS last_paid_at,
                -- 구독 시작 이후 사용된 크레딧 합계 (경고: 15% 이상 사용 체크용)
                (
                    SELECT COALESCE(SUM(ABS(cl.amount)), 0)
                    FROM credit_ledger cl
                    WHERE cl.user_id = s.user_id
                      AND cl.amount < 0
                      AND cl.created_at >= s.created_at
                ) AS credits_used_since_start
            FROM subscriptions s
            JOIN plans p ON p.plan_id = s.plan_id
            WHERE s.user_id = CAST(:user_id AS uuid)
              AND s.status = 'active'
            ORDER BY p.plan_rank DESC, s.current_period_end DESC NULLS LAST, s.created_at DESC
        """
        active_rows = db.execute(text(active_query), {"user_id": user_id}).fetchall()

        attempts_query = """
            SELECT
                billing_attempt_id,
                subscription_id,
                plan_change_id,
                attempt_type,
                status,
                amount,
                payment_id,
                failure_message,
                attempted_at
            FROM subscription_billing_attempts
            WHERE user_id = CAST(:user_id AS uuid)
            ORDER BY attempted_at DESC, created_at DESC
            LIMIT 30
        """
        attempt_rows = db.execute(text(attempts_query), {"user_id": user_id}).fetchall()

        changes_query = """
            SELECT
                pc.plan_change_id,
                pc.change_type,
                pc.status,
                pc.apply_timing,
                pc.effective_at,
                pc.applied_at,
                pc.created_at,
                pc.from_subscription_id,
                pc.to_subscription_id,
                fp.plan_code AS from_plan_code,
                fp.plan_name AS from_plan_name,
                tp.plan_code AS to_plan_code,
                tp.plan_name AS to_plan_name
            FROM subscription_plan_changes pc
            LEFT JOIN subscriptions fs ON fs.subscription_id = pc.from_subscription_id
            LEFT JOIN plans fp ON fp.plan_id = fs.plan_id
            LEFT JOIN plans tp ON tp.plan_id = pc.to_plan_id
            WHERE pc.user_id = CAST(:user_id AS uuid)
            ORDER BY pc.created_at DESC
            LIMIT 30
        """
        change_rows = db.execute(text(changes_query), {"user_id": user_id}).fetchall()

        from datetime import datetime, timezone

        active_subscriptions = []
        for row in active_rows:
            m = row._mapping

            # 결제일 경과 일수 계산 (경고 판단용)
            last_paid_at = m["last_paid_at"]
            days_since_last_payment = None
            if last_paid_at:
                now_utc = datetime.now(timezone.utc)
                paid_utc = last_paid_at.replace(tzinfo=timezone.utc) if last_paid_at.tzinfo is None else last_paid_at
                days_since_last_payment = (now_utc - paid_utc).days

            # 크레딧 사용률 계산 (경고 판단용)
            plan_credits = int(m["plan_credits"] or 0)
            credits_used = int(m["credits_used_since_start"] or 0)
            credit_used_ratio = round(credits_used / plan_credits * 100, 1) if plan_credits > 0 else 0.0

            active_subscriptions.append({
                "subscription_id": str(m["subscription_id"]),
                "plan_id": str(m["plan_id"]),
                "plan_code": m["plan_code"],
                "plan_name": m["plan_name"],
                "plan_credits": plan_credits,
                "status": m["status"],
                "current_period_start": m["current_period_start"].isoformat() if m["current_period_start"] else None,
                "current_period_end": m["current_period_end"].isoformat() if m["current_period_end"] else None,
                "next_billing_at": m["next_billing_at"].isoformat() if m["next_billing_at"] else None,
                "auto_renew": bool(m["auto_renew"]),
                "cancel_at_period_end": bool(m["cancel_at_period_end"]),
                "cancelled_at": m["cancelled_at"].isoformat() if m["cancelled_at"] else None,
                "billing_status": m["billing_status"],
                "carried_over_days": int(m["carried_over_days"] or 0),
                "superseded_by_subscription_id": str(m["superseded_by_subscription_id"]) if m["superseded_by_subscription_id"] else None,
                "original_period_end": m["original_period_end"].isoformat() if m["original_period_end"] else None,
                "upgraded_at": m["upgraded_at"].isoformat() if m["upgraded_at"] else None,
                "created_at": m["created_at"].isoformat() if m["created_at"] else None,
                # 경고 판단용 필드
                "last_paid_at": last_paid_at.isoformat() if last_paid_at else None,
                "days_since_last_payment": days_since_last_payment,
                "credit_used_ratio": credit_used_ratio,
            })

        billing_attempts = []
        for row in attempt_rows:
            m = row._mapping
            billing_attempts.append({
                "attempt_id": str(m["billing_attempt_id"]),
                "subscription_id": str(m["subscription_id"]) if m["subscription_id"] else None,
                "plan_change_id": str(m["plan_change_id"]) if m["plan_change_id"] else None,
                "attempt_type": m["attempt_type"],
                "status": m["status"],
                "amount": m["amount"],
                "payment_id": str(m["payment_id"]) if m["payment_id"] else None,
                "failure_reason": m["failure_message"],
                "attempted_at": m["attempted_at"].isoformat() if m["attempted_at"] else None,
            })

        plan_changes = []
        for row in change_rows:
            m = row._mapping
            plan_changes.append({
                "plan_change_id": str(m["plan_change_id"]),
                "change_type": m["change_type"],
                "status": m["status"],
                "apply_timing": m["apply_timing"],
                "effective_at": m["effective_at"].isoformat() if m["effective_at"] else None,
                "applied_at": m["applied_at"].isoformat() if m["applied_at"] else None,
                "created_at": m["created_at"].isoformat() if m["created_at"] else None,
                "from_subscription_id": str(m["from_subscription_id"]) if m["from_subscription_id"] else None,
                "to_subscription_id": str(m["to_subscription_id"]) if m["to_subscription_id"] else None,
                "from_plan_code": m["from_plan_code"],
                "from_plan_name": m["from_plan_name"],
                "to_plan_code": m["to_plan_code"],
                "to_plan_name": m["to_plan_name"],
            })

        return {
            "user": {
                "user_id": str(current["user_id"]),
                "email": current["email"] or "",
            },
            "current_applied_plan": {
                "plan_code": current["current_plan_code"] or current["free_plan_code"] or "free",
                "plan_name": current["current_plan_name"] or current["free_plan_name"] or "Free",
                "subscription_id": str(current["subscription_id"]) if current["subscription_id"] else None,
                "subscription_status": current["subscription_status"] or "free",
                "current_period_start": current["current_period_start"].isoformat() if current["current_period_start"] else None,
                "current_period_end": current["current_period_end"].isoformat() if current["current_period_end"] else None,
                "next_billing_at": current["next_billing_at"].isoformat() if current["next_billing_at"] else None,
                "auto_renew": bool(current["auto_renew"]) if current["subscription_id"] else False,
                "cancel_at_period_end": bool(current["cancel_at_period_end"]) if current["subscription_id"] else False,
                "cancelled_at": current["cancelled_at"].isoformat() if current["cancelled_at"] else None,
                "billing_status": current["billing_status"],
                "carried_over_days": int(current["carried_over_days"] or 0),
                "superseded_by_subscription_id": str(current["superseded_by_subscription_id"]) if current["superseded_by_subscription_id"] else None,
            },
            "active_subscriptions": active_subscriptions,
            "billing_attempts": billing_attempts,
            "plan_changes": plan_changes,
        }
    finally:
        db.close()


def get_users_list(page: int = 1, limit: int = 20, role: str = None, status_val: str = None):
    db = SessionLocal()
    try:
        offset = (page - 1) * limit
        params = {"limit": limit, "offset": offset}

        conditions = []
        if role:
            conditions.append("u.role = :role")
            params["role"] = role
        if status_val:
            conditions.append("u.status = :status_val")
            params["status_val"] = status_val

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        rows = db.execute(
            text(f"""
                SELECT
                    u.user_id,
                    u.email,
                    u.role,
                    u.status,
                    u.created_at,
                    oa.provider
                FROM users u
                LEFT JOIN oauth_accounts oa ON oa.user_id = u.user_id
                {where}
                ORDER BY u.created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).fetchall()

        counts = db.execute(
            text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status = 'active')    AS active,
                    COUNT(*) FILTER (WHERE status = 'suspended') AS suspended,
                    COUNT(*) FILTER (WHERE status = 'deleted')   AS deleted
                FROM users
            """)
        ).fetchone()

        users = []
        for row in rows:
            m = row._mapping
            users.append(
                {
                    "user_id": str(m["user_id"]),
                    "email": m["email"] or "",
                    "role": m["role"],
                    "status": m["status"],
                    "created_at": m["created_at"].strftime("%Y.%m.%d") if m["created_at"] else "",
                    "provider": m["provider"] or "",
                }
            )

        cm = counts._mapping
        return {
            "users": users,
            "total": cm["total"],
            "active": cm["active"],
            "suspended": cm["suspended"],
            "deleted": cm["deleted"],
            "page": page,
            "limit": limit,
        }
    finally:
        db.close()


def get_admin_policies():
    db = SessionLocal()
    try:
        # 1. Load default policies as base structure
        policies = {key: value.copy() if isinstance(value, dict) else value for key, value in DEFAULT_ADMIN_POLICIES.items()}
        
        # Deep copy plans sub-dictionaries to avoid mutating global DEFAULT_ADMIN_POLICIES
        for group in ["file_processing", "payment", "retention"]:
            if group in policies and "plans" in policies[group]:
                policies[group]["plans"] = {
                    pk: pv.copy() for pk, pv in policies[group]["plans"].items()
                }

        # 2. Query admin_policy_settings for plan-independent policies (e.g. allowedFormats, notification)
        rows = db.execute(
            text("""
                SELECT policy_key, policy_value
                FROM admin_policy_settings
                ORDER BY policy_key
            """)
        ).fetchall()

        for row in rows:
            item = row._mapping
            db_val = item["policy_value"]
            if item["policy_key"] in policies:
                if isinstance(db_val, dict):
                    for k, v in db_val.items():
                        # Do not overwrite the 'plans' key with db_val since we fetch plans from plans table
                        if k != "plans":
                            policies[item["policy_key"]][k] = v
                else:
                    policies[item["policy_key"]] = db_val

        # 3. Query plans table to populate plan-dependent policies
        plan_rows = db.execute(
            text("""
                SELECT
                    plan_code,
                    plan_name,
                    badge_label,
                    badge_class,
                    description,
                    file_size_limit,
                    max_jobs,
                    monthly_quota,
                    result_retention_days,
                    price_amount,
                    watermark_required,
                    auto_delete_original_hours,
                    metadata_retention_days,
                    credits,
                    status,
                    sort_order
                FROM plans
                WHERE status = 'active'
                ORDER BY sort_order ASC, created_at ASC
            """)
        ).fetchall()

        for prow in plan_rows:
            pm = prow._mapping
            pcode = pm["plan_code"].lower()
            common = {
                "name": pm["plan_name"],
                "badgeLabel": pm["badge_label"],
                "badgeClass": pm["badge_class"],
                "description": pm["description"],
                "sortOrder": pm["sort_order"],
                "status": pm["status"],
            }
            policies["file_processing"]["plans"][pcode] = {
                **common,
                "fileSizeLimit": pm["file_size_limit"],
                "maxJobs": pm["max_jobs"],
                "monthlyQuota": pm["monthly_quota"],
                "resultRetention": pm["result_retention_days"],
                "watermarkRequired": pm["watermark_required"],
            }
            policies["payment"]["plans"][pcode] = {
                **common,
                "credits": pm["credits"],
                "price": pm["price_amount"],
            }
            policies["retention"]["plans"][pcode] = {
                **common,
                "autoDeleteOriginalHours": pm["auto_delete_original_hours"],
                "metadataRetentionDays": pm["metadata_retention_days"],
            }

        # 4. Query credit_plans table to populate creditPlans
        credit_plan_rows = db.execute(
            text("""
                SELECT
                    credit_plan_code,
                    credit_plan_name,
                    base_credits,
                    bonus_credits,
                    expires_days,
                    price_amount,
                    status,
                    sort_order
                FROM credit_plans
                WHERE status = 'active'
                ORDER BY sort_order ASC, created_at ASC
            """)
        ).fetchall()

        credit_plans_map = {}
        for crow in credit_plan_rows:
            cm = crow._mapping
            credit_plans_map[cm["credit_plan_code"]] = {
                "name": cm["credit_plan_name"],
                "credits": cm["base_credits"],
                "bonusCredits": cm["bonus_credits"],
                "expiresDays": cm["expires_days"],
                "price": cm["price_amount"],
                "status": cm["status"],
                "sortOrder": cm["sort_order"],
            }

        if credit_plans_map:
            policies["payment"]["creditPlans"] = credit_plans_map

        return policies
    finally:
        db.close()


def update_admin_policies(policies: dict, updated_by=None):
    db = SessionLocal()
    try:
        # 1. Extract and update plan-dependent policies in the plans table
        file_processing_plans = policies.get("file_processing", {}).get("plans", {})
        payment_plans = policies.get("payment", {}).get("plans", {})
        retention_plans = policies.get("retention", {}).get("plans", {})

        all_plan_codes = set(file_processing_plans.keys()) | set(payment_plans.keys()) | set(retention_plans.keys())
        for plan_code in all_plan_codes:
            fp_plan = file_processing_plans.get(plan_code, {})
            pay_plan = payment_plans.get(plan_code, {})
            ret_plan = retention_plans.get(plan_code, {})

            db.execute(
                text("""
                    UPDATE plans
                    SET file_size_limit = :file_size_limit,
                        max_jobs = :max_jobs,
                        monthly_quota = :monthly_quota,
                        result_retention_days = :result_retention_days,
                        price_amount = :price_amount,
                        auto_delete_original_hours = :auto_delete_original_hours,
                        metadata_retention_days = :metadata_retention_days,
                        credits = :credits,
                        watermark_required = :watermark_required
                    WHERE plan_code = :plan_code
                """),
                {
                    "plan_code": plan_code,
                    "file_size_limit": fp_plan.get("fileSizeLimit"),
                    "max_jobs": fp_plan.get("maxJobs"),
                    "monthly_quota": fp_plan.get("monthlyQuota"),
                    "result_retention_days": fp_plan.get("resultRetention"),
                    "price_amount": pay_plan.get("price"),
                    "auto_delete_original_hours": ret_plan.get("autoDeleteOriginalHours"),
                    "metadata_retention_days": ret_plan.get("metadataRetentionDays"),
                    "credits": pay_plan.get("credits"),
                    "watermark_required": fp_plan.get("watermarkRequired")
                }
            )

        # 2. Update admin_policy_settings for plan-independent policies
        # Save file_processing (allowedFormats only)
        file_proc_val = {
            "allowedFormats": policies.get("file_processing", {}).get("allowedFormats", [])
        }
        db.execute(
            text("""
                INSERT INTO admin_policy_settings (policy_key, policy_value, updated_by, created_at, updated_at)
                VALUES (:policy_key, CAST(:policy_value AS jsonb), :updated_by, now(), now())
                ON CONFLICT (policy_key) DO UPDATE
                SET policy_value = EXCLUDED.policy_value,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = now()
            """),
            {
                "policy_key": "file_processing",
                "policy_value": json.dumps(file_proc_val, ensure_ascii=False),
                "updated_by": updated_by,
            }
        )

        # Save notification if provided
        notify_val = policies.get("notification", {})
        if notify_val:
            db.execute(
                text("""
                    INSERT INTO admin_policy_settings (policy_key, policy_value, updated_by, created_at, updated_at)
                    VALUES (:policy_key, CAST(:policy_value AS jsonb), :updated_by, now(), now())
                    ON CONFLICT (policy_key) DO UPDATE
                    SET policy_value = EXCLUDED.policy_value,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = now()
                """),
                {
                    "policy_key": "notification",
                    "policy_value": json.dumps(notify_val, ensure_ascii=False),
                    "updated_by": updated_by,
                }
            )

        # 3. Write into audit_logs table
        db.execute(
            text("""
                INSERT INTO audit_logs (
                    actor_user_id,
                    actor_type,
                    action,
                    target_type,
                    detail,
                    created_at
                )
                VALUES (
                    :actor_user_id,
                    'admin',
                    'update_policy',
                    'policy',
                    CAST(:detail AS jsonb),
                    now()
                )
            """),
            {
                "actor_user_id": updated_by,
                "detail": json.dumps(policies, ensure_ascii=False)
            }
        )

        db.commit()
        return get_admin_policies()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_payments_list(
    product_type: str = None,
    status: str = None,
    q: str = None,
    search_key: str = "email",
    date_from: str = None,
    date_to: str = None,
    page: int = 1,
    limit: int = 10,
):
    db = SessionLocal()
    try:
        conditions = []
        params = {}

        if product_type and product_type != "all":
            conditions.append("p.product_type = :product_type")
            params["product_type"] = product_type

        if status and status != "all":
            conditions.append("p.status = :status")
            params["status"] = status

        if date_from:
            conditions.append("p.created_at >= CAST(:date_from AS date)")
            params["date_from"] = date_from

        if date_to:
            conditions.append("p.created_at < CAST(:date_to AS date) + INTERVAL '1 day'")
            params["date_to"] = date_to

        if q:
            val = f"%{q.lower()}%"
            params["q"] = val
            if search_key == "email":
                conditions.append("LOWER(u.email) LIKE :q")
            elif search_key == "payment_id":
                conditions.append("CAST(p.payment_id AS varchar) LIKE :q")
            elif search_key == "user_id":
                conditions.append("CAST(p.user_id AS varchar) LIKE :q")
            elif search_key == "product_name":
                conditions.append("(LOWER(p.order_name) LIKE :q OR LOWER(pl.plan_name) LIKE :q OR LOWER(cp.credit_plan_name) LIKE :q)")
            else:
                conditions.append(
                    "(LOWER(u.email) LIKE :q OR CAST(p.payment_id AS varchar) LIKE :q OR CAST(p.user_id AS varchar) LIKE :q OR LOWER(p.order_name) LIKE :q)"
                )

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        total_query = f"""
            SELECT COUNT(*)
            FROM payments p
            LEFT JOIN users u ON u.user_id = p.user_id
            LEFT JOIN plans pl ON pl.plan_id = p.plan_id
            LEFT JOIN credit_plans cp ON cp.credit_plan_id = p.credit_plan_id
            {where_clause}
        """
        total = db.execute(text(total_query), params).scalar() or 0

        offset = (page - 1) * limit
        list_query = f"""
            SELECT
                p.payment_id,
                p.paid_at,
                p.requested_at,
                p.created_at,
                p.user_id,
                u.email AS user_email,
                p.product_type,
                COALESCE(p.order_name, pl.plan_name, cp.credit_plan_name) AS product_name,
                p.amount,
                p.status,
                p.payment_method,
                p.pg_provider
            FROM payments p
            LEFT JOIN users u ON u.user_id = p.user_id
            LEFT JOIN plans pl ON pl.plan_id = p.plan_id
            LEFT JOIN credit_plans cp ON cp.credit_plan_id = p.credit_plan_id
            {where_clause}
            ORDER BY p.created_at DESC, p.payment_id DESC
            LIMIT :limit OFFSET :offset
        """
        rows = db.execute(text(list_query), {**params, "limit": limit, "offset": offset}).fetchall()

        summary_query = """
            SELECT
                COALESCE(SUM(amount) FILTER (WHERE status = 'success' AND created_at >= CURRENT_DATE), 0) AS today_amount,
                COUNT(*) FILTER (WHERE status = 'success') AS success_count,
                COUNT(*) FILTER (WHERE status IN ('refunded', 'canceled')) AS refund_count,
                COUNT(*) FILTER (WHERE product_type = 'credit' AND status = 'success') AS credit_count
            FROM payments
        """
        sum_row = db.execute(text(summary_query)).fetchone()
        sm = sum_row._mapping if sum_row else {}

        summary = {
            "today_amount": int(sm.get("today_amount") or 0),
            "success_count": int(sm.get("success_count") or 0),
            "refund_count": int(sm.get("refund_count") or 0),
            "credit_count": int(sm.get("credit_count") or 0),
        }

        data = []
        for row in rows:
            m = row._mapping
            data.append({
                "payment_id": str(m["payment_id"]),
                "paid_at": m["paid_at"].isoformat() if m["paid_at"] else (m["created_at"].isoformat() if m["created_at"] else ""),
                "requested_at": m["requested_at"].isoformat() if m["requested_at"] else "",
                "user_id": str(m["user_id"]),
                "user_email": m["user_email"] or "",
                "product_type": m["product_type"],
                "product_name": m["product_name"] or "",
                "amount": m["amount"],
                "status": m["status"],
                "payment_method": m["payment_method"] or "",
                "pg_provider": m["pg_provider"] or "",
            })

        return {
            "data": data,
            "summary": summary,
            "total": total,
            "page": page,
            "limit": limit,
        }
    finally:
        db.close()


def get_payment_detail(payment_id: str):
    db = SessionLocal()
    try:
        query = """
            SELECT
                p.payment_id,
                p.paid_at,
                p.requested_at,
                p.approved_at,
                p.refunded_at,
                p.created_at,
                p.user_id,
                u.email AS user_email,
                p.product_type,
                COALESCE(p.order_name, pl.plan_name, cp.credit_plan_name) AS product_name,
                p.amount,
                p.balance_amount,
                p.status,
                p.payment_method,
                p.pg_provider,
                p.subscription_id,
                (SELECT cl.ledger_id FROM credit_ledger cl WHERE cl.source_id = p.payment_id LIMIT 1) AS credit_ledger_id,
                (SELECT cl.amount FROM credit_ledger cl WHERE cl.source_id = p.payment_id LIMIT 1) AS credit_amount,
                -- 해당 결제로 충전된 크레딧의 충전 시각
                (SELECT cl.created_at FROM credit_ledger cl WHERE cl.source_id = p.payment_id LIMIT 1) AS credit_charged_at,
                -- 해당 결제 충전 이후 사용자가 사용한 크레딧 합계 (spend 항목, 음수 amount의 절댓값 합산)
                (
                    SELECT COALESCE(SUM(ABS(cl2.amount)), 0)
                    FROM credit_ledger cl2
                    WHERE cl2.user_id = p.user_id
                      AND cl2.amount < 0
                      AND cl2.created_at >= (
                          SELECT cl3.created_at FROM credit_ledger cl3
                          WHERE cl3.source_id = p.payment_id LIMIT 1
                      )
                ) AS credit_used_after_charge
            FROM payments p
            LEFT JOIN users u ON u.user_id = p.user_id
            LEFT JOIN plans pl ON pl.plan_id = p.plan_id
            LEFT JOIN credit_plans cp ON cp.credit_plan_id = p.credit_plan_id
            WHERE p.payment_id = CAST(:payment_id AS uuid)
        """
        row = db.execute(text(query), {"payment_id": payment_id}).fetchone()
        if not row:
            raise ValueError("결제 내역을 찾을 수 없습니다.")

        m = row._mapping

        # 결제일로부터 경과 일수 계산
        from datetime import datetime, timezone
        paid_at = m["paid_at"] or m["created_at"]
        days_since_payment = 0
        if paid_at:
            now_utc = datetime.now(timezone.utc)
            paid_utc = paid_at.replace(tzinfo=timezone.utc) if paid_at.tzinfo is None else paid_at
            days_since_payment = (now_utc - paid_utc).days

        # 크레딧 사용률 계산 (충전 크레딧 대비 충전 이후 사용량 비율)
        credit_amount = int(m["credit_amount"] or 0)
        credit_used_after = int(m["credit_used_after_charge"] or 0)
        credit_used_ratio = round(credit_used_after / credit_amount * 100, 1) if credit_amount > 0 else 0.0

        return {
            "payment_id": str(m["payment_id"]),
            "paid_at": m["paid_at"].isoformat() if m["paid_at"] else (m["created_at"].isoformat() if m["created_at"] else ""),
            "requested_at": m["requested_at"].isoformat() if m["requested_at"] else "",
            "approved_at": m["approved_at"].isoformat() if m["approved_at"] else "",
            "refunded_at": m["refunded_at"].isoformat() if m["refunded_at"] else None,
            "user_id": str(m["user_id"]),
            "user_email": m["user_email"] or "",
            "product_type": m["product_type"],
            "product_name": m["product_name"] or "",
            "amount": m["amount"],
            "balance_amount": m["balance_amount"] if m["balance_amount"] is not None else m["amount"],
            "status": m["status"],
            "payment_method": m["payment_method"] or "",
            "pg_provider": m["pg_provider"] or "",
            "subscription_id": str(m["subscription_id"]) if m["subscription_id"] else None,
            "credit_ledger_id": str(m["credit_ledger_id"]) if m["credit_ledger_id"] else None,
            "credit_amount": credit_amount,
            # 환불 경고 판단용 필드
            "days_since_payment": days_since_payment,        # 결제일 경과 일수
            "credit_used_ratio": credit_used_ratio,          # 크레딧 사용률 (%)
            "admin_note": "정상 결제 건입니다.",
        }
    finally:
        db.close()


def refund_payment(payment_id: str, admin_user_id: str = None, refund_reason: str = None):
    db = SessionLocal()
    try:
        # 결제 정보 조회 (크레딧 차감을 위해 user_id, credit_amount 포함)
        query = """
            SELECT p.payment_id, p.status, p.amount, p.balance_amount,
                   p.user_id,
                   (SELECT cl.amount FROM credit_ledger cl WHERE cl.source_id = p.payment_id LIMIT 1) AS credit_amount
            FROM payments p
            WHERE p.payment_id = CAST(:payment_id AS uuid)
        """
        row = db.execute(text(query), {"payment_id": payment_id}).fetchone()
        if not row:
            raise ValueError("결제 내역을 찾을 수 없습니다.")

        m = row._mapping
        current_status = str(m["status"]).lower()
        if current_status in ("refunded", "canceled"):
            raise ValueError("이미 환불/취소 처리된 결제입니다.")

        # payments 상태를 refunded로 업데이트 + refund_reason 저장
        db.execute(
            text("""
                UPDATE payments
                SET status = 'refunded',
                    refunded_at = NOW(),
                    balance_amount = 0,
                    refund_reason = :refund_reason,
                    updated_at = NOW()
                WHERE payment_id = CAST(:payment_id AS uuid)
            """),
            {"payment_id": payment_id, "refund_reason": refund_reason}
        )

        # 결제로 충전된 크레딧이 있으면 차감 (0 이하로 내려가지 않도록 GREATEST 처리)
        credit_amount = int(m["credit_amount"] or 0)
        if credit_amount > 0:
            db.execute(
                text("""
                    UPDATE user_credit_balances
                    SET balance = GREATEST(balance - :amount, 0),
                        updated_at = NOW()
                    WHERE user_id = :user_id
                """),
                {"user_id": str(m["user_id"]), "amount": credit_amount}
            )
            # 차감 후 잔액 조회
            bal_row = db.execute(
                text("SELECT balance FROM user_credit_balances WHERE user_id = :user_id"),
                {"user_id": str(m["user_id"])}
            ).fetchone()
            balance_after = int(bal_row._mapping["balance"]) if bal_row else 0

            # credit_ledger에 차감 이력 기록
            db.execute(
                text("""
                    INSERT INTO credit_ledger (
                        user_id, amount, balance_after,
                        entry_type, source_type, source_id, description, created_at
                    ) VALUES (
                        :user_id, :amount, :balance_after,
                        'refund_deduct', 'payment', CAST(:source_id AS uuid),
                        :description, NOW()
                    )
                """),
                {
                    "user_id": str(m["user_id"]),
                    "amount": -credit_amount,
                    "balance_after": balance_after,
                    "source_id": payment_id,
                    "description": f"환불 처리 크레딧 차감 (사유: {refund_reason or '미입력'})",
                }
            )

        detail = {
            "payment_id": payment_id,
            "amount": m["amount"],
            "refund_reason": refund_reason,
            "credit_deducted": credit_amount,
            "action": "refund_payment"
        }
        db.execute(
            text("""
                INSERT INTO audit_logs (
                    actor_user_id,
                    actor_type,
                    action,
                    target_type,
                    detail,
                    created_at
                )
                VALUES (
                    :actor_user_id,
                    'admin',
                    'refund_payment',
                    'payment',
                    CAST(:detail AS jsonb),
                    NOW()
                )
            """),
            {
                "actor_user_id": admin_user_id,
                "detail": json.dumps(detail, ensure_ascii=False)
            }
        )

        db.commit()
        return {"payment_id": payment_id, "status": "refunded", "credit_deducted": credit_amount}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def cancel_subscription_for_user(user_id: str, subscription_id: str, cancel_reason: str = None):
    """
    관리자용 구독 강제 취소.
    - 해당 구독을 cancelled 처리 (cancel_reason 기록)
    - 취소된 구독을 superseded(대체)했던 이전 구독이 있으면 복원 시도
      (이전 구독 period_end > now이면 active 복원, 만료면 Free 유지)
    """
    from datetime import datetime, timezone

    db = SessionLocal()
    try:
        # 1. 취소할 구독 조회 (해당 사용자 소유 + active 상태 확인, 크레딧 차감을 위해 plans.credits 포함)
        sub = db.execute(
            text("""
                SELECT s.subscription_id, s.user_id, s.plan_id, s.status,
                       s.current_period_end, s.superseded_by_subscription_id,
                       p.plan_code, p.plan_name, p.credits AS plan_credits
                FROM subscriptions s
                JOIN plans p ON p.plan_id = s.plan_id
                WHERE s.subscription_id = CAST(:sub_id AS uuid)
                  AND s.user_id = CAST(:user_id AS uuid)
                  AND s.status = 'active'
            """),
            {"sub_id": subscription_id, "user_id": user_id},
        ).fetchone()

        if not sub:
            raise ValueError("취소할 구독을 찾을 수 없습니다.")

        sub = sub._mapping

        # 2. 해당 구독 → cancelled 처리 (취소 사유 함께 기록)
        db.execute(
            text("""
                UPDATE subscriptions
                SET status = 'cancelled',
                    cancelled_at = NOW(),
                    cancel_at_period_end = FALSE,
                    auto_renew = FALSE,
                    cancel_reason = :cancel_reason
                WHERE subscription_id = CAST(:sub_id AS uuid)
            """),
            {"sub_id": subscription_id, "cancel_reason": cancel_reason},
        )

        # 2-1. 해당 플랜의 크레딧 차감 (0 이하로 내려가지 않도록 GREATEST 처리)
        plan_credits = int(sub["plan_credits"] or 0)
        if plan_credits > 0:
            db.execute(
                text("""
                    UPDATE user_credit_balances
                    SET balance = GREATEST(balance - :amount, 0),
                        updated_at = NOW()
                    WHERE user_id = CAST(:user_id AS uuid)
                """),
                {"user_id": user_id, "amount": plan_credits}
            )
            # 차감 후 잔액 조회
            bal_row = db.execute(
                text("SELECT balance FROM user_credit_balances WHERE user_id = CAST(:user_id AS uuid)"),
                {"user_id": user_id}
            ).fetchone()
            balance_after = int(bal_row._mapping["balance"]) if bal_row else 0

            # credit_ledger에 차감 이력 기록
            db.execute(
                text("""
                    INSERT INTO credit_ledger (
                        user_id, amount, balance_after,
                        entry_type, source_type, source_id, description, created_at
                    ) VALUES (
                        CAST(:user_id AS uuid), :amount, :balance_after,
                        'cancel_deduct', 'subscription', CAST(:source_id AS uuid),
                        :description, NOW()
                    )
                """),
                {
                    "user_id": user_id,
                    "amount": -plan_credits,
                    "balance_after": balance_after,
                    "source_id": subscription_id,
                    "description": f"구독 취소 크레딧 차감 - {sub['plan_name']} (사유: {cancel_reason or '미입력'})",
                }
            )

        # 3. 이전 구독 탐색 — 이 구독에 의해 superseded 된 구독을 역방향으로 찾음
        #    (Pro를 Studio로 업그레이드하면 Pro.superseded_by = Studio.id 로 설정됨)
        restored_plan = None
        prev_sub = db.execute(
            text("""
                SELECT s.subscription_id, s.status, s.current_period_end,
                       p.plan_code, p.plan_name
                FROM subscriptions s
                JOIN plans p ON p.plan_id = s.plan_id
                WHERE s.user_id = CAST(:user_id AS uuid)
                  AND s.superseded_by_subscription_id = CAST(:sub_id AS uuid)
                ORDER BY s.current_period_end DESC NULLS LAST
                LIMIT 1
            """),
            {"user_id": user_id, "sub_id": subscription_id},
        ).fetchone()

        if prev_sub:
            prev = prev_sub._mapping
            period_end = prev["current_period_end"]
            now_utc = datetime.now(timezone.utc)
            # period_end가 미래이면 이전 구독 복원
            if period_end and period_end.replace(tzinfo=timezone.utc) > now_utc:
                db.execute(
                    text("""
                        UPDATE subscriptions
                        SET status = 'active',
                            cancelled_at = NULL,
                            superseded_by_subscription_id = NULL
                        WHERE subscription_id = CAST(:prev_id AS uuid)
                    """),
                    {"prev_id": str(prev["subscription_id"])},
                )
                restored_plan = prev["plan_name"]

        db.commit()
        return {
            "message": "구독이 취소되었습니다.",
            "cancelled_plan": sub["plan_name"],
            "restored_plan": restored_plan or "Free",
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# =========================================================================
# 관리자 - 사용자 모니터링 (Admin Monitoring)
#   - /admin/monitoring/overview : 상단 메트릭 집계
#   - /admin/monitoring/activities : 실시간 활동 중인 사용자 목록(상세 포함)
#   - /admin/monitoring/jobs/{job_id}/cancel : 진행 중 작업 강제 취소
# 모든 수치는 실제 DB(analysis_jobs, uploads, users, user_login_histories,
# subscriptions, plans)에서 집계한다.
# =========================================================================

# analysis_jobs.status -> 프론트 STATUS_META 키 매핑
# (processing / queued / done / error / idle)
_JOB_STATUS_TO_FRONT = {
    "processing": "processing",
    "retrying":   "processing",
    "queued":     "queued",
    "completed":  "done",
    "failed":     "error",
    "cancelled":  "idle",
    "cancelling": "idle",
}


def _format_elapsed(seconds):
    """초(float) -> 'm:ss' 형식 문자열. None/음수는 '—' 반환."""
    if seconds is None or seconds < 0:
        return "—"
    total = int(seconds)
    minutes, sec = divmod(total, 60)
    return f"{minutes}:{sec:02d}"


def _relative_time(seconds):
    """경과 초(float) -> '방금 전 / N분 전 / N시간 전' 한글 상대 시간."""
    if seconds is None:
        return "—"
    s = int(seconds)
    if s < 60:
        return "방금 전"
    if s < 3600:
        return f"{s // 60}분 전"
    if s < 86400:
        return f"{s // 3600}시간 전"
    return f"{s // 86400}일 전"


def get_monitoring_overview():
    """사용자 모니터링 상단 메트릭 집계.

    - 현재 접속자: 최근 15분 내 로그인 성공 이력이 있는 고유 사용자 수
    - 처리 중 / 대기 중: analysis_jobs 상태별 건수
    - 평균 대기: 현재 대기(queued) 작업들의 생성 후 경과 시간 평균(초)
    - 금일 완료 / 오류: 오늘(서버 날짜) 완료·실패한 작업 수
    - 플랜 분포: 현재 처리 중 작업의 플랜별 분포
    """
    db = SessionLocal()
    try:
        # 1) 작업 상태 집계 + 1시간 전 접속자 비교용
        job_stats = db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'processing')                                    AS processing,
                    COUNT(*) FILTER (WHERE status = 'queued')                                         AS queued,
                    COUNT(*) FILTER (WHERE status = 'completed' AND completed_at::date = now()::date) AS today_done,
                    COUNT(*) FILTER (WHERE status = 'failed'    AND updated_at::date  = now()::date)  AS today_error,
                    AVG(EXTRACT(EPOCH FROM (now() - created_at)))
                        FILTER (WHERE status = 'queued')                                              AS avg_wait_sec
                FROM analysis_jobs
            """)
        ).fetchone()._mapping

        # 2) 현재 접속자(최근 15분 로그인 성공) / 1시간 전 시점 비교
        online = db.execute(
            text("""
                SELECT
                    COUNT(DISTINCT user_id) FILTER (
                        WHERE logged_in_at >= now() - interval '15 minutes'
                    ) AS current_online,
                    COUNT(DISTINCT user_id) FILTER (
                        WHERE logged_in_at >= now() - interval '75 minutes'
                          AND logged_in_at <  now() - interval '60 minutes'
                    ) AS prev_online
                FROM user_login_histories
                WHERE login_result = 'success'
                  AND user_id IS NOT NULL
            """)
        ).fetchone()._mapping

        # 3) 처리 중 작업의 플랜별 분포 (활성 구독 기준, 없으면 Free)
        plan_rows = db.execute(
            text("""
                SELECT COALESCE(p.plan_name, 'Free') AS plan_name, COUNT(*) AS cnt
                FROM analysis_jobs j
                LEFT JOIN LATERAL (
                    SELECT s.plan_id
                    FROM subscriptions s
                    WHERE s.user_id = j.user_id AND s.status = 'active'
                    ORDER BY s.started_at DESC
                    LIMIT 1
                ) sub ON true
                LEFT JOIN plans p ON p.plan_id = sub.plan_id
                WHERE j.status = 'processing'
                GROUP BY COALESCE(p.plan_name, 'Free')
                ORDER BY cnt DESC
            """)
        ).fetchall()
        plan_breakdown = {r._mapping["plan_name"]: r._mapping["cnt"] for r in plan_rows}

        today_done = job_stats["today_done"] or 0
        today_error = job_stats["today_error"] or 0
        total_today = today_done + today_error
        error_rate = round((today_error / total_today) * 100, 1) if total_today else 0.0

        current_online = online["current_online"] or 0
        prev_online = online["prev_online"] or 0

        return {
            "current_online": current_online,
            "online_delta": current_online - prev_online,
            "processing": job_stats["processing"] or 0,
            "queued": job_stats["queued"] or 0,
            "avg_wait_seconds": int(job_stats["avg_wait_sec"]) if job_stats["avg_wait_sec"] else 0,
            "today_completed": today_done,
            "today_error": today_error,
            "error_rate": error_rate,
            "plan_breakdown": plan_breakdown,
        }
    finally:
        db.close()


def get_monitoring_activities(limit: int = 50, status_filter: str = None):
    """실시간 활동 중인 사용자 목록.

    각 사용자별로 '가장 최근 작업' 1건을 대표로 보여준다.
    최근 24시간 내 작업이 있는 사용자를 활동 중으로 간주한다.
    프론트 카드(상세 패널)에 필요한 모든 필드를 함께 반환한다.
    """
    db = SessionLocal()
    try:
        # 1) 사용자별 최신 작업 1건 (DISTINCT ON) + 경과 시간(초)을 DB에서 직접 계산
        rows = db.execute(
            text("""
                SELECT * FROM (
                    SELECT DISTINCT ON (j.user_id)
                        j.job_id,
                        j.user_id,
                        j.status,
                        j.job_type,
                        j.total_progress,
                        u.email,
                        u.created_at AS joined_at,
                        up.original_filename,
                        up.media_type,
                        -- 진행 중: 시작~현재 / 완료·실패: 시작~완료 까지의 실제 소요 시간
                        EXTRACT(EPOCH FROM (
                            COALESCE(j.completed_at, now()) - COALESCE(j.started_at, j.created_at)
                        )) AS elapsed_sec,
                        EXTRACT(EPOCH FROM (now() - COALESCE(j.updated_at, j.created_at)))   AS last_seen_sec
                    FROM analysis_jobs j
                    JOIN users u        ON u.user_id = j.user_id
                    LEFT JOIN uploads up ON up.upload_id = j.upload_id
                    WHERE j.created_at >= now() - interval '24 hours'
                    ORDER BY j.user_id, j.updated_at DESC NULLS LAST, j.created_at DESC
                ) t
                ORDER BY t.last_seen_sec ASC
                LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()

        if not rows:
            return {"activities": [], "total": 0}

        user_ids = [r._mapping["user_id"] for r in rows]

        # 2) 사용자별 플랜(활성 구독) 매핑
        plan_map = {}
        plan_rows = db.execute(
            text("""
                SELECT DISTINCT ON (s.user_id) s.user_id, p.plan_name
                FROM subscriptions s
                JOIN plans p ON p.plan_id = s.plan_id
                WHERE s.user_id = ANY(:uids) AND s.status = 'active'
                ORDER BY s.user_id, s.started_at DESC
            """),
            {"uids": user_ids},
        ).fetchall()
        for r in plan_rows:
            plan_map[r._mapping["user_id"]] = r._mapping["plan_name"]

        # 3) 사용자별 금일/누적 처리 건수
        count_map = {}
        count_rows = db.execute(
            text("""
                SELECT
                    user_id,
                    COUNT(*)                                              AS total_jobs,
                    COUNT(*) FILTER (WHERE created_at::date = now()::date) AS today_jobs
                FROM analysis_jobs
                WHERE user_id = ANY(:uids)
                GROUP BY user_id
            """),
            {"uids": user_ids},
        ).fetchall()
        for r in count_rows:
            m = r._mapping
            count_map[m["user_id"]] = {"total": m["total_jobs"], "today": m["today_jobs"]}

        # 4) 사용자별 최근 로그인(세션 시작·IP·UA)
        login_map = {}
        login_rows = db.execute(
            text("""
                SELECT DISTINCT ON (user_id) user_id, ip_address, user_agent, logged_in_at
                FROM user_login_histories
                WHERE user_id = ANY(:uids) AND login_result = 'success'
                ORDER BY user_id, logged_in_at DESC
            """),
            {"uids": user_ids},
        ).fetchall()
        for r in login_rows:
            m = r._mapping
            login_map[m["user_id"]] = m

        # 4-b) 사용자별 최근 5개 작업 이력(recent_events용)
        # 한 번에 전체 조회 후 Python에서 user_id별 최대 5개 슬라이싱
        recent_jobs_map: dict = {uid: [] for uid in user_ids}
        recent_rows = db.execute(
            text("""
                SELECT j.user_id, j.status, j.job_type, j.created_at, j.completed_at,
                       up.original_filename, up.media_type
                FROM analysis_jobs j
                LEFT JOIN uploads up ON up.upload_id = j.upload_id
                WHERE j.user_id = ANY(:uids)
                  AND j.created_at >= now() - interval '7 days'
                ORDER BY j.user_id, j.created_at DESC
            """),
            {"uids": user_ids},
        ).fetchall()
        for r in recent_rows:
            rm = r._mapping
            uid = rm["user_id"]
            if uid not in recent_jobs_map:
                continue
            if len(recent_jobs_map[uid]) >= 5:
                continue
            status_label = {
                "completed": "처리 완료",
                "failed":    "오류 발생",
                "cancelled": "작업 취소",
                "processing": "처리 중",
                "queued":    "대기 중",
            }.get(rm["status"], rm["status"])
            fname = rm["original_filename"] or ""
            mtype = rm["media_type"] or ""
            label = f"{status_label} — {fname}" if fname else status_label
            if mtype:
                label += f" ({mtype})"
            ts_dt = rm["completed_at"] or rm["created_at"]
            ts_str = ts_dt.strftime("%H:%M:%S") if ts_dt else "—"
            recent_jobs_map[uid].append({"ts": ts_str, "label": label, "status": rm["status"]})

        # 5) 행 가공
        activities = []
        for r in rows:
            m = r._mapping
            uid = m["user_id"]
            front_status = _JOB_STATUS_TO_FRONT.get(m["status"], "idle")
            has_file = bool(m["original_filename"])

            login = login_map.get(uid)
            counts = count_map.get(uid, {"total": 0, "today": 0})

            # IP 마스킹: 끝 두 옥텟을 가린다 (개인정보 보호)
            ip_masked = "—"
            if login and login["ip_address"]:
                parts = str(login["ip_address"]).split(".")
                if len(parts) == 4:
                    ip_masked = f"{parts[0]}.{parts[1]}.***.***"
                else:
                    ip_masked = str(login["ip_address"])

            session_start = login["logged_in_at"].strftime("%H:%M:%S") if login and login["logged_in_at"] else "—"

            # 최근 활동 이벤트: 세션 시작을 맨 앞에 붙이고 최근 작업 이력을 최대 5개로 구성
            events = []
            if session_start != "—":
                events.append({"ts": session_start, "label": "세션 시작", "status": "session"})
            events.extend(recent_jobs_map.get(uid, []))
            events = events[:5]  # 최대 5개

            activities.append({
                "id": str(uid),
                "job_id": str(m["job_id"]),
                "email": m["email"] or "(이메일 없음)",
                "plan": plan_map.get(uid, "Free"),
                "status": front_status,
                "job_file": m["original_filename"] if has_file else "—",
                "job_type": m["media_type"] or "" if has_file else "",
                "progress": m["total_progress"] or 0,
                "elapsed": _format_elapsed(m["elapsed_sec"]) if front_status != "idle" else "—",
                "last_seen": _relative_time(m["last_seen_sec"]),
                "ip": ip_masked,
                "ua": (login["user_agent"][:60] if login and login["user_agent"] else "—"),
                "joined": m["joined_at"].strftime("%Y.%m.%d") if m["joined_at"] else "—",
                "today_jobs": counts["today"],
                "total_jobs": counts["total"],
                "session_start": session_start,
                "recent_events": events,
            })

        # status_filter 가 지정되면 해당 상태만 반환
        if status_filter:
            activities = [a for a in activities if a["status"] == status_filter]

        return {"activities": activities, "total": len(activities)}
    finally:
        db.close()


# =========================================================================
# 관리자 - 컴플라이언스 (Admin Compliance)
#   - /admin/compliance/overview  : 자동삭제 탭 (정책 현황 + 삭제 예정 + 최근 로그)
#   - /admin/compliance/search    : 처리 이력 검색 (job_id / user_id / watermark)
#   - /admin/compliance/consent   : 약관 동의 이력 (user_id 또는 email)
#   - /admin/compliance/reports   : 신고·수사 응답 이력 (abuse_reports)
# =========================================================================

def get_compliance_overview():
    """컴플라이언스 자동삭제 탭 데이터.

    - 데이터 종류별 잔존 건수 및 준수율
    - 24h 내 삭제 예정 집계
    - 최근 24시간 자동 삭제 로그
    """
    db = SessionLocal()
    try:
        # 1) 원본 파일 잔존 수 & 만료 초과(미삭제) 수
        orig_row = db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE deleted_at IS NULL)            AS total,
                    COUNT(*) FILTER (WHERE deleted_at IS NULL
                                       AND expires_at IS NOT NULL
                                       AND expires_at < now())            AS overdue
                FROM uploads
            """)
        ).fetchone()._mapping
        orig_total  = int(orig_row["total"]  or 0)
        orig_overdue= int(orig_row["overdue"] or 0)
        orig_rate   = round((1 - orig_overdue / orig_total) * 100, 1) if orig_total else 100.0

        # 2) 결과 파일 잔존 수 & 만료 초과 수
        pf_row = db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE deleted_at IS NULL)            AS total,
                    COUNT(*) FILTER (WHERE deleted_at IS NULL
                                       AND expires_at IS NOT NULL
                                       AND expires_at < now())            AS overdue
                FROM processed_files
            """)
        ).fetchone()._mapping
        pf_total   = int(pf_row["total"]  or 0)
        pf_overdue = int(pf_row["overdue"] or 0)
        pf_rate    = round((1 - pf_overdue / pf_total) * 100, 1) if pf_total else 100.0

        # 3) 처리 이력 메타데이터 (analysis_jobs) 건수 및 90일 초과 수
        meta_row = db.execute(
            text("""
                SELECT
                    COUNT(*)                                              AS total,
                    COUNT(*) FILTER (
                        WHERE created_at < now() - interval '90 days'
                    )                                                     AS overdue
                FROM analysis_jobs
            """)
        ).fetchone()._mapping
        meta_total  = int(meta_row["total"]  or 0)
        meta_overdue= int(meta_row["overdue"] or 0)
        meta_rate   = round((1 - meta_overdue / meta_total) * 100, 1) if meta_total else 100.0

        # 4) 탈퇴 회원 식별 정보 (유예 중: deleted 상태이지만 7일 미경과)
        deleted_row = db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (
                        WHERE status = 'deleted'
                          AND updated_at >= now() - interval '7 days'
                    ) AS pending_delete,
                    COUNT(*) FILTER (
                        WHERE status = 'deleted'
                          AND updated_at < now() - interval '7 days'
                    ) AS overdue_delete
                FROM users
            """)
        ).fetchone()._mapping
        pending_delete = int(deleted_row["pending_delete"] or 0)
        overdue_delete = int(deleted_row["overdue_delete"] or 0)
        deleted_rate = 100.0 if overdue_delete == 0 else round(
            pending_delete / (pending_delete + overdue_delete) * 100, 1
        )

        # 5) 24h 내 삭제 예정 집계
        upcoming_row = db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (
                        WHERE deleted_at IS NULL
                          AND expires_at IS NOT NULL
                          AND expires_at BETWEEN now() AND now() + interval '24 hours'
                    ) AS uploads_due,
                    COUNT(*) FILTER (
                        WHERE deleted_at IS NULL
                          AND expires_at IS NOT NULL
                          AND expires_at BETWEEN now() AND now() + interval '24 hours'
                    ) AS pf_due
                FROM uploads
            """)
        ).fetchone()._mapping

        pf_upcoming_row = db.execute(
            text("""
                SELECT COUNT(*) AS pf_due
                FROM processed_files
                WHERE deleted_at IS NULL
                  AND expires_at IS NOT NULL
                  AND expires_at BETWEEN now() AND now() + interval '24 hours'
            """)
        ).fetchone()._mapping

        uploads_due = int(upcoming_row["uploads_due"] or 0)
        pf_due      = int(pf_upcoming_row["pf_due"]   or 0)

        # 6) 최근 24시간 삭제 로그 (최신 30건)
        log_rows = db.execute(
            text("""
                SELECT
                    target_type,
                    delete_reason,
                    deleted_at,
                    result,
                    error_message,
                    actor_type,
                    created_at
                FROM deletion_events
                WHERE created_at >= now() - interval '24 hours'
                ORDER BY created_at DESC
                LIMIT 30
            """)
        ).fetchall()

        logs = []
        for r in log_rows:
            m = r._mapping
            ts = m["deleted_at"] or m["created_at"]
            logs.append({
                "ts": ts.strftime("%H:%M:%S") if ts else "—",
                "target_type": m["target_type"] or "",
                "delete_reason": m["delete_reason"] or "",
                "result": m["result"] or "success",
                "error_message": m["error_message"] or "",
                "actor_type": m["actor_type"] or "system",
            })

        return {
            "policy_status": [
                {
                    "label": "업로드 원본 파일",
                    "sub": "모든 플랜 공통",
                    "policy": "처리 후 12h",
                    "count": orig_total,
                    "compliance_rate": orig_rate,
                },
                {
                    "label": "치환 결과 파일",
                    "sub": "플랜별 보존 기간",
                    "policy": "3~90일",
                    "count": pf_total,
                    "compliance_rate": pf_rate,
                },
                {
                    "label": "처리 이력 메타데이터",
                    "sub": "워터마크 역추적용",
                    "policy": "90일",
                    "count": meta_total,
                    "compliance_rate": meta_rate,
                },
                {
                    "label": "탈퇴 회원 식별 정보",
                    "sub": "7일 유예 후 영구 삭제",
                    "policy": "탈퇴 + 7d",
                    "count": pending_delete,
                    "count_label": f"{pending_delete}개 (유예 중)",
                    "compliance_rate": deleted_rate,
                },
            ],
            "upcoming": {
                "uploads_due": uploads_due,
                "pf_due": pf_due,
                "total": uploads_due + pf_due,
            },
            "recent_logs": logs,
        }
    finally:
        db.close()


def search_compliance(q: str, search_type: str = "job_id"):
    """처리 이력 검색.

    search_type:
      - job_id      : analysis_jobs.job_id (UUID 일부)
      - user_id     : users.email 또는 user_id (최근 작업)
      - watermark   : abuse_reports.watermark_hash
    q가 비어 있으면 최근 50건 반환 (기본 목록).
    """
    # q 없으면 최근 작업 10건 반환
    if not q or not q.strip():
        db = SessionLocal()
        try:
            rows = db.execute(
                text("""
                    SELECT
                        j.job_id, j.user_id, j.status, j.job_type,
                        j.detection_count, j.created_at, j.completed_at,
                        u.email,
                        up.original_filename, up.content_type,
                        up.file_size,
                        COALESCE(j.duration_seconds, up.duration_seconds) AS duration_seconds,
                        COALESCE(j.width,  up.width)  AS width,
                        COALESCE(j.height, up.height) AS height,
                        up.media_type
                    FROM analysis_jobs j
                    JOIN users u ON u.user_id = j.user_id
                    LEFT JOIN uploads up ON up.upload_id = j.upload_id
                    ORDER BY j.created_at DESC
                    LIMIT 10
                """)
            ).fetchall()
            results = [_build_job_result(r._mapping) for r in rows]
            return {"results": results, "total": len(results), "is_default": True}
        finally:
            db.close()

    db = SessionLocal()
    try:
        results = []

        if search_type == "job_id":
            rows = db.execute(
                text("""
                    SELECT
                        j.job_id,
                        j.user_id,
                        j.status,
                        j.job_type,
                        j.detection_count,
                        j.created_at,
                        j.completed_at,
                        u.email,
                        up.original_filename,
                        up.content_type,
                        up.file_size,
                        COALESCE(j.duration_seconds, up.duration_seconds) AS duration_seconds,
                        COALESCE(j.width,  up.width)  AS width,
                        COALESCE(j.height, up.height) AS height,
                        up.media_type
                    FROM analysis_jobs j
                    JOIN users u ON u.user_id = j.user_id
                    LEFT JOIN uploads up ON up.upload_id = j.upload_id
                    WHERE CAST(j.job_id AS text) ILIKE :q
                    ORDER BY j.created_at DESC
                    LIMIT 10
                """),
                {"q": f"%{q.strip()}%"},
            ).fetchall()

            for r in rows:
                m = r._mapping
                results.append(_build_job_result(m))

        elif search_type == "user_id":
            # email 또는 user_id 부분 일치
            rows = db.execute(
                text("""
                    SELECT
                        j.job_id,
                        j.user_id,
                        j.status,
                        j.job_type,
                        j.detection_count,
                        j.created_at,
                        j.completed_at,
                        u.email,
                        up.original_filename,
                        up.content_type,
                        up.file_size,
                        COALESCE(j.duration_seconds, up.duration_seconds) AS duration_seconds,
                        COALESCE(j.width,  up.width)  AS width,
                        COALESCE(j.height, up.height) AS height,
                        up.media_type
                    FROM analysis_jobs j
                    JOIN users u ON u.user_id = j.user_id
                    LEFT JOIN uploads up ON up.upload_id = j.upload_id
                    WHERE LOWER(u.email) ILIKE :q
                       OR CAST(j.user_id AS text) ILIKE :q
                    ORDER BY j.created_at DESC
                    LIMIT 20
                """),
                {"q": f"%{q.strip().lower()}%"},
            ).fetchall()

            for r in rows:
                m = r._mapping
                results.append(_build_job_result(m))

        elif search_type == "watermark":
            rows = db.execute(
                text("""
                    SELECT
                        ar.report_id,
                        ar.watermark_hash,
                        ar.report_type,
                        ar.description,
                        ar.status,
                        ar.created_at,
                        ar.resolved_at,
                        u.email AS reporter_email
                    FROM abuse_reports ar
                    LEFT JOIN users u ON u.user_id = ar.reporter_user_id
                    WHERE ar.watermark_hash ILIKE :q
                    ORDER BY ar.created_at DESC
                    LIMIT 10
                """),
                {"q": f"%{q.strip()}%"},
            ).fetchall()

            for r in rows:
                m = r._mapping
                results.append({
                    "type": "abuse_report",
                    "report_id": str(m["report_id"]),
                    "watermark_hash": m["watermark_hash"] or "",
                    "report_type": m["report_type"] or "",
                    "description": m["description"] or "",
                    "status": m["status"] or "",
                    "reporter_email": m["reporter_email"] or "—",
                    "created_at": m["created_at"].strftime("%Y.%m.%d %H:%M:%S") if m["created_at"] else "—",
                    "resolved_at": m["resolved_at"].strftime("%Y.%m.%d %H:%M:%S") if m["resolved_at"] else None,
                })

        return {"results": results, "total": len(results)}
    finally:
        db.close()


def _build_job_result(m):
    """analysis_jobs 행 → 검색 결과 dict."""
    jid = str(m["job_id"])
    # duration_seconds → "mm:ss" 형식
    dur = m["duration_seconds"]
    dur_str = "—"
    if dur:
        mm, ss = divmod(int(dur), 60)
        dur_str = f"{mm:02d}:{ss:02d}"

    sz = m["file_size"]
    sz_str = "—"
    if sz:
        if sz >= 1024 ** 3:
            sz_str = f"{sz / 1024 ** 3:.1f} GB"
        elif sz >= 1024 ** 2:
            sz_str = f"{sz / 1024 ** 2:.1f} MB"
        else:
            sz_str = f"{sz / 1024:.1f} KB"

    res = m["width"] and m["height"]
    resolution = f"{m['width']}×{m['height']}" if res else "—"

    return {
        "type": "job",
        "job_id": jid,
        "short_id": f"j_{jid[:4]}...{jid[-4:]}",
        "email": m["email"] or "—",
        "user_id": str(m["user_id"]),
        "status": m["status"] or "—",
        "detection_count": int(m["detection_count"] or 0),
        "created_at": m["created_at"].strftime("%Y.%m.%d %H:%M:%S") if m["created_at"] else "—",
        "completed_at": m["completed_at"].strftime("%Y.%m.%d %H:%M:%S") if m["completed_at"] else "—",
        "filename": m["original_filename"] or "—",
        "content_type": m["content_type"] or "—",
        "media_type": m["media_type"] or "—",
        "file_size": sz_str,
        "duration": dur_str,
        "resolution": resolution,
    }


def get_consent_history(q: str):
    """약관 동의 이력 조회.

    q: email 또는 user_id (UUID 일부)
    q가 비어 있으면 최근 50건 반환 (기본 목록).
    """
    type_labels = {
        "terms_of_service": "서비스 이용약관",
        "privacy_policy":   "개인정보처리방침",
        "marketing":        "마케팅 정보 수신",
        "ai_training":      "AI 학습 동의",
    }

    # q 없으면 최근 동의 이력 50건 반환 (모든 사용자)
    if not q or not q.strip():
        db = SessionLocal()
        try:
            rows = db.execute(
                text("""
                    SELECT
                        uc.consent_type,
                        uc.is_agreed,
                        uc.version,
                        uc.source,
                        uc.created_at,
                        u.email,
                        u.user_id
                    FROM user_consents uc
                    JOIN users u ON u.user_id = uc.user_id
                    ORDER BY uc.created_at DESC
                    LIMIT 50
                """)
            ).fetchall()
            consents = []
            for r in rows:
                m = r._mapping
                ctype = m["consent_type"] or ""
                consents.append({
                    "consent_type": ctype,
                    "type_label": type_labels.get(ctype, ctype),
                    "is_agreed": bool(m["is_agreed"]),
                    "version": m["version"] or "",
                    "source": m["source"] or "",
                    "email": m["email"] or "",
                    "user_id": str(m["user_id"]),
                    "created_at": m["created_at"].strftime("%Y.%m.%d %H:%M") if m["created_at"] else "—",
                })
            return {"user": None, "consents": consents, "is_default": True}
        finally:
            db.close()

    db = SessionLocal()
    try:
        # 사용자 찾기 (email 정확 일치 또는 uuid 부분 일치)
        user_row = db.execute(
            text("""
                SELECT user_id, email, status, created_at
                FROM users
                WHERE LOWER(email) = LOWER(:email)
                   OR CAST(user_id AS text) ILIKE :q
                LIMIT 1
            """),
            {"email": q.strip(), "q": f"%{q.strip()}%"},
        ).fetchone()

        if not user_row:
            return {"user": None, "consents": [], "error": "사용자를 찾을 수 없습니다."}

        um = user_row._mapping
        uid = um["user_id"]

        # 동의 이력
        consent_rows = db.execute(
            text("""
                SELECT
                    consent_type,
                    is_agreed,
                    version,
                    source,
                    created_at
                FROM user_consents
                WHERE user_id = :uid
                ORDER BY created_at ASC
            """),
            {"uid": uid},
        ).fetchall()

        # consent_type 한글 레이블 매핑
        type_labels = {
            "terms_of_service": "서비스 이용약관",
            "privacy_policy":   "개인정보처리방침",
            "marketing":        "마케팅 정보 수신",
            "ai_training":      "AI 학습 동의",
        }

        consents = []
        for r in consent_rows:
            m = r._mapping
            ctype = m["consent_type"] or ""
            consents.append({
                "consent_type": ctype,
                "type_label": type_labels.get(ctype, ctype),
                "is_agreed": bool(m["is_agreed"]),
                "version": m["version"] or "",
                "source": m["source"] or "",
                "created_at": m["created_at"].strftime("%Y.%m.%d %H:%M") if m["created_at"] else "—",
            })

        return {
            "user": {
                "user_id": str(uid),
                "email": um["email"] or "",
                "status": um["status"] or "",
                "joined_at": um["created_at"].strftime("%Y.%m.%d") if um["created_at"] else "—",
            },
            "consents": consents,
        }
    finally:
        db.close()


def get_compliance_reports(page: int = 1, limit: int = 20):
    """신고·수사 응답 이력 (abuse_reports) 목록."""
    db = SessionLocal()
    try:
        page = max(int(page or 1), 1)
        limit = min(int(limit or 20), 100)
        offset = (page - 1) * limit

        total = db.execute(text("SELECT COUNT(*) FROM abuse_reports")).scalar() or 0

        rows = db.execute(
            text("""
                SELECT
                    ar.report_id,
                    ar.watermark_hash,
                    ar.report_type,
                    ar.description,
                    ar.status,
                    ar.created_at,
                    ar.resolved_at,
                    u.email AS reporter_email
                FROM abuse_reports ar
                LEFT JOIN users u ON u.user_id = ar.reporter_user_id
                ORDER BY ar.created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {"limit": limit, "offset": offset},
        ).fetchall()

        # report_type 한글 레이블
        type_labels = {
            "forgery":       "위변조 신고",
            "court_order":   "법원 명령",
            "investigation": "수사 협조",
            "takedown":      "삭제 요청",
        }

        data = []
        for r in rows:
            m = r._mapping
            rtype = m["report_type"] or ""
            data.append({
                "report_id": str(m["report_id"]),
                "watermark_hash": m["watermark_hash"] or "—",
                "report_type": rtype,
                "type_label": type_labels.get(rtype, rtype or "기타"),
                "description": (m["description"] or "")[:100],
                "status": m["status"] or "received",
                "reporter_email": m["reporter_email"] or "—",
                "created_at": m["created_at"].strftime("%Y.%m.%d") if m["created_at"] else "—",
                "resolved_at": m["resolved_at"].strftime("%Y.%m.%d") if m["resolved_at"] else None,
            })

        return {"data": data, "total": total, "page": page, "limit": limit}
    finally:
        db.close()


# =========================================================================
# 관리자 - 처리 큐 (Admin Queue)
#   - /admin/queue/overview : 메트릭 + 작업목록 + 워커 + 차트 데이터 일괄 반환
# =========================================================================

def get_queue_overview():
    """처리 큐 페이지에 필요한 모든 실시간 데이터를 한번에 반환.

    - 메트릭 6종 (현재 큐, 평균 대기, 시간당 완료, 실패율, 활성 워커)
    - 처리 중/대기 중 작업 목록 (최대 50건)
    - GPU 워커 상태 (최근 5분 내 heartbeat 기준)
    - 24h 시간별 완료 건수 (차트용)
    """
    db = SessionLocal()
    try:
        # 1) 메트릭 집계
        metric_row = db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'queued')                                         AS queued,
                    COUNT(*) FILTER (WHERE status IN ('processing','retrying'))                       AS processing,
                    AVG(EXTRACT(EPOCH FROM (now() - created_at)))
                        FILTER (WHERE status = 'queued')                                              AS avg_wait_sec,
                    COUNT(*) FILTER (
                        WHERE status = 'completed'
                          AND completed_at >= now() - interval '1 hour'
                    )                                                                                  AS throughput_last_hour,
                    COUNT(*) FILTER (
                        WHERE status = 'failed'
                          AND updated_at >= now() - interval '24 hours'
                    )                                                                                  AS failed_24h,
                    COUNT(*) FILTER (
                        WHERE status IN ('completed','failed')
                          AND updated_at >= now() - interval '24 hours'
                    )                                                                                  AS done_24h
                FROM analysis_jobs
            """)
        ).fetchone()._mapping

        queued     = int(metric_row["queued"] or 0)
        processing = int(metric_row["processing"] or 0)
        avg_wait   = int(metric_row["avg_wait_sec"] or 0)
        throughput = int(metric_row["throughput_last_hour"] or 0)
        failed_24h = int(metric_row["failed_24h"] or 0)
        done_24h   = int(metric_row["done_24h"] or 0)
        error_rate = round(failed_24h / done_24h * 100, 1) if done_24h else 0.0

        # 2) 처리 중/대기 중 작업의 플랜별 건수
        plan_cnt_rows = db.execute(
            text("""
                SELECT COALESCE(p.plan_name, 'Free') AS plan_name, COUNT(*) AS cnt
                FROM analysis_jobs j
                LEFT JOIN LATERAL (
                    SELECT s.plan_id
                    FROM subscriptions s
                    WHERE s.user_id = j.user_id AND s.status = 'active'
                    ORDER BY s.started_at DESC NULLS LAST
                    LIMIT 1
                ) sub ON true
                LEFT JOIN plans p ON p.plan_id = sub.plan_id
                WHERE j.status IN ('queued','processing','retrying')
                GROUP BY COALESCE(p.plan_name, 'Free')
            """)
        ).fetchall()
        plan_counts = {r._mapping["plan_name"]: int(r._mapping["cnt"]) for r in plan_cnt_rows}

        # 3) 활성 워커 (최근 5분 내 heartbeat 기준)
        worker_rows = db.execute(
            text("""
                SELECT DISTINCT ON (worker_id)
                    worker_id,
                    worker_type,
                    current_stage,
                    progress_percent,
                    ngrok_url,
                    heartbeat_at,
                    EXTRACT(EPOCH FROM (now() - heartbeat_at)) AS since_sec
                FROM job_worker_heartbeats
                WHERE heartbeat_at >= now() - interval '5 minutes'
                  AND worker_id IS NOT NULL
                ORDER BY worker_id, heartbeat_at DESC
            """)
        ).fetchall()

        workers = []
        for r in worker_rows:
            m = r._mapping
            workers.append({
                "worker_id": m["worker_id"],
                "worker_type": m["worker_type"] or "colab",
                "stage": m["current_stage"] or "—",
                "progress": int(m["progress_percent"] or 0),
                "ngrok_url": m["ngrok_url"] or "",
                "last_beat_seconds": int(m["since_sec"] or 0),
            })
        active_workers = len(workers)

        # 4) 처리 중/대기 중 작업 목록 (최대 50건, 우선순위: processing 먼저, 이후 queued)
        job_rows = db.execute(
            text("""
                SELECT
                    j.job_id,
                    j.user_id,
                    j.status,
                    j.job_type,
                    j.total_progress,
                    j.queue_position,
                    j.detection_count,
                    j.created_at,
                    j.started_at,
                    u.email,
                    up.original_filename,
                    up.media_type,
                    EXTRACT(EPOCH FROM (
                        COALESCE(now(), j.started_at) - COALESCE(j.started_at, j.created_at)
                    )) AS elapsed_sec,
                    COALESCE(p.plan_name, 'Free') AS plan_name
                FROM analysis_jobs j
                JOIN users u ON u.user_id = j.user_id
                LEFT JOIN uploads up ON up.upload_id = j.upload_id
                LEFT JOIN LATERAL (
                    SELECT s.plan_id
                    FROM subscriptions s
                    WHERE s.user_id = j.user_id AND s.status = 'active'
                    ORDER BY s.started_at DESC NULLS LAST
                    LIMIT 1
                ) sub ON true
                LEFT JOIN plans p ON p.plan_id = sub.plan_id
                WHERE j.status IN ('queued','processing','retrying')
                ORDER BY
                    CASE j.status WHEN 'processing' THEN 0 WHEN 'retrying' THEN 1 ELSE 2 END,
                    j.queue_position ASC NULLS LAST,
                    j.created_at ASC
                LIMIT 50
            """)
        ).fetchall()

        jobs = []
        for r in job_rows:
            m = r._mapping
            # 짧은 job_id (앞 8자...끝 3자)
            jid_str = str(m["job_id"])
            short_jid = f"j_{jid_str[:4]}...{jid_str[-3:]}"
            jobs.append({
                "job_id": jid_str,
                "short_id": short_jid,
                "email": m["email"] or "",
                "status": m["status"],
                "plan": m["plan_name"],
                "filename": m["original_filename"] or "—",
                "media_type": m["media_type"] or "",
                "progress": int(m["total_progress"] or 0),
                "elapsed": _format_elapsed(m["elapsed_sec"]),
                "queue_position": m["queue_position"],
                "detection_count": int(m["detection_count"] or 0),
            })

        # 5) 24h 시간별 완료 건수 (차트용, 0~23시 배열)
        hourly_rows = db.execute(
            text("""
                SELECT
                    DATE_PART('hour', completed_at AT TIME ZONE 'Asia/Seoul') AS hr,
                    COUNT(*) AS cnt
                FROM analysis_jobs
                WHERE status = 'completed'
                  AND completed_at >= now() - interval '24 hours'
                GROUP BY hr
            """)
        ).fetchall()
        hourly = [0] * 24
        for r in hourly_rows:
            m = r._mapping
            hr = int(m["hr"] or 0)
            if 0 <= hr < 24:
                hourly[hr] = int(m["cnt"] or 0)

        return {
            "metrics": {
                "total_queue": queued + processing,
                "queued": queued,
                "processing": processing,
                "avg_wait_seconds": avg_wait,
                "throughput_last_hour": throughput,
                "error_rate": error_rate,
                "active_workers": active_workers,
                "plan_counts": plan_counts,
            },
            "jobs": jobs,
            "workers": workers,
            "hourly_throughput": hourly,
        }
    finally:
        db.close()


def cancel_monitoring_job(job_id: str, admin_user_id: str = None):
    """관리자 모니터링 화면에서 진행 중 작업을 강제 취소한다.

    analysis_jobs.cancel_requested 플래그를 세워 워커가 안전하게 중단하도록 한다.
    이미 완료/실패/취소된 작업은 변경하지 않는다.
    """
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT status FROM analysis_jobs WHERE job_id = CAST(:jid AS uuid)"),
            {"jid": job_id},
        ).fetchone()
        if row is None:
            raise ValueError("해당 작업을 찾을 수 없습니다.")

        current = row._mapping["status"]
        if current in ("completed", "failed", "cancelled"):
            return {"job_id": job_id, "status": current, "cancel_requested": False}

        db.execute(
            text("""
                UPDATE analysis_jobs
                SET cancel_requested = true,
                    status = 'cancelling',
                    message = '관리자에 의해 취소 요청됨',
                    updated_at = now()
                WHERE job_id = CAST(:jid AS uuid)
            """),
            {"jid": job_id},
        )

        # 감사 로그 기록 (관리자 행위 추적)
        db.execute(
            text("""
                INSERT INTO audit_logs (actor_user_id, actor_type, action, target_type, target_id, detail)
                VALUES (
                    CAST(:aid AS uuid), 'admin', 'job_cancel', 'analysis_job',
                    CAST(:jid AS uuid), CAST(:detail AS jsonb)
                )
            """),
            {
                "aid": admin_user_id,
                "jid": job_id,
                "detail": json.dumps({"prev_status": current, "via": "admin_monitoring"}),
            },
        )

        db.commit()
        return {"job_id": job_id, "status": "cancelling", "cancel_requested": True}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

