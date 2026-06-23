from sqlalchemy import text


def create_payment_query(conn, data):
    return conn.execute(
        text("""
        INSERT INTO payments (
            user_id,
            subscription_id,
            amount,
            status,
            pg_provider,
            pg_transaction_id,
            last_transaction_key,
            order_name,
            payment_method,
            easy_pay_provider,
            toss_status,
            total_amount,
            balance_amount,
            currency,
            requested_at,
            approved_at,
            receipt_url,
            is_partial_cancelable,
            paid_at,
            created_at,
            updated_at
        )
        VALUES (
            :user_id,
            :subscription_id,
            :amount,
            :status,
            'toss',
            :pg_transaction_id,
            :last_transaction_key,
            :order_name,
            :payment_method,
            :easy_pay_provider,
            :toss_status,
            :total_amount,
            :balance_amount,
            :currency,
            :requested_at,
            :approved_at,
            :receipt_url,
            :is_partial_cancelable,
            :paid_at,
            NOW(),
            NOW()
        )
        RETURNING *
        """),
        data,
    ).fetchone()
