from sqlalchemy import text


def get_setting_query(conn, user_id):
    return conn.execute(
        text("""
            SELECT
                user_id,
                email_notification,
                browser_notification,
                data_usage_consent,
                created_at,
                updated_at
            FROM user_settings
            WHERE user_id = :user_id
        """),
        {"user_id": user_id},
    ).fetchone()


def create_setting_query(conn, user_id):
    conn.execute(
        text("""
            INSERT INTO user_settings (
                user_id
            )
            VALUES (
                :user_id
            )
        """),
        {"user_id": user_id},
    )


def update_setting_query(
    conn,
    user_id,
    email_notification,
    browser_notification,
    data_usage_consent,
):
    conn.execute(
        text("""
            UPDATE user_settings
            SET
                email_notification = :email_notification,
                browser_notification = :browser_notification,
                data_usage_consent = :data_usage_consent,
                updated_at = NOW()
            WHERE user_id = :user_id
        """),
        {
            "user_id": user_id,
            "email_notification": email_notification,
            "browser_notification": browser_notification,
            "data_usage_consent": data_usage_consent,
        },
    )