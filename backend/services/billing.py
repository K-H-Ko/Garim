import hashlib
import hmac
import os

from sqlalchemy import text
from sqlalchemy.orm import Session


def _to_iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _row_mapping(row):
    if not row:
        return None
    return row._mapping if hasattr(row, "_mapping") else row


def _encryption_secret():
    secret = os.getenv("BILLING_KEY_ENCRYPTION_SECRET")
    if not secret:
        raise ValueError("BILLING_KEY_ENCRYPTION_SECRET is required.")
    if len(secret) < 32:
        raise ValueError("BILLING_KEY_ENCRYPTION_SECRET must be at least 32 characters.")
    return secret


def _billing_key_hash(billing_key: str, secret: str):
    return hmac.new(
        secret.encode("utf-8"),
        billing_key.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _mask_card_number(value: str | None):
    if not value:
        return None
    compact = "".join(ch for ch in value if ch.isdigit() or ch == "*")
    if "*" in compact:
        return compact
    if len(compact) <= 4:
        return f"****{compact}"
    return f"****{compact[-4:]}"


def _public_billing_key(row):
    return {
        "billing_key_id": str(row["billing_key_id"]) if row.get("billing_key_id") else None,
        "pg_provider": row.get("pg_provider"),
        "customer_key": row.get("customer_key"),
        "card_company": row.get("card_company"),
        "masked_card_number": row.get("masked_card_number"),
        "method_type": row.get("method_type"),
        "status": row.get("status"),
        "last_used_at": _to_iso(row.get("last_used_at")),
        "revoked_at": _to_iso(row.get("revoked_at")),
        "created_at": _to_iso(row.get("created_at")),
    }


def save_billing_key(
    db: Session,
    user_id: str,
    billing_key: str,
    customer_key: str | None = None,
    card_company: str | None = None,
    masked_card_number: str | None = None,
    method_type: str | None = None,
    pg_provider: str = "toss",
):
    secret = _encryption_secret()
    billing_hash = _billing_key_hash(billing_key, secret)
    masked = _mask_card_number(masked_card_number)
    method = method_type or "unknown"

    row = db.execute(
        text("""
            INSERT INTO billing_keys (
                user_id,
                pg_provider,
                encrypted_billing_key,
                billing_key_hash,
                customer_key,
                card_company,
                masked_card_number,
                method_type,
                status,
                created_at,
                updated_at
            )
            VALUES (
                :user_id,
                :pg_provider,
                encode(pgp_sym_encrypt(:billing_key, :secret), 'base64'),
                :billing_key_hash,
                :customer_key,
                :card_company,
                :masked_card_number,
                :method_type,
                'active',
                NOW(),
                NOW()
            )
            RETURNING
                billing_key_id,
                pg_provider,
                customer_key,
                card_company,
                masked_card_number,
                method_type,
                status,
                last_used_at,
                revoked_at,
                created_at
        """),
        {
            "user_id": user_id,
            "pg_provider": pg_provider,
            "billing_key": billing_key,
            "secret": secret,
            "billing_key_hash": billing_hash,
            "customer_key": customer_key,
            "card_company": card_company,
            "masked_card_number": masked,
            "method_type": method,
        },
    ).fetchone()
    return _public_billing_key(_row_mapping(row))


def list_billing_keys(db: Session, user_id: str):
    rows = db.execute(
        text("""
            SELECT
                billing_key_id,
                pg_provider,
                customer_key,
                card_company,
                masked_card_number,
                method_type,
                status,
                last_used_at,
                revoked_at,
                created_at
            FROM billing_keys
            WHERE user_id = :user_id
            ORDER BY
                CASE WHEN status = 'active' THEN 0 ELSE 1 END,
                created_at DESC
        """),
        {"user_id": user_id},
    ).fetchall()

    return [_public_billing_key(_row_mapping(row)) for row in rows]


def get_active_billing_key_for_charge(
    db: Session,
    user_id: str,
    billing_key_id=None,
):
    secret = _encryption_secret()
    id_filter = (
        "AND billing_key_id = :billing_key_id"
        if billing_key_id
        else ""
    )
    row = db.execute(
        text(f"""
            SELECT
                billing_key_id,
                pg_provider,
                customer_key,
                card_company,
                masked_card_number,
                method_type,
                pgp_sym_decrypt(decode(encrypted_billing_key, 'base64'), :secret) AS billing_key
            FROM billing_keys
            WHERE user_id = :user_id
              AND status = 'active'
              {id_filter}
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {
            "user_id": user_id,
            "billing_key_id": billing_key_id,
            "secret": secret,
        },
    ).fetchone()
    return _row_mapping(row)
