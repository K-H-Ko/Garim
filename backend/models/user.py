from sqlalchemy import text


def get_user_by_provider_query(conn, provider, provider_user_id, provider_email=None):
    return conn.execute(
        text(
            """
            SELECT
                u.user_id AS id,
                oa.provider,
                oa.provider_user_id,
                oa.provider_email,
                u.email,
                u.display_name AS name,
                u.profile_image_url,
                u.role,
                u.status
            FROM oauth_accounts oa
            JOIN users u ON u.user_id = oa.user_id
            WHERE oa.provider = :provider
              AND (
                (
                  :provider_email IS NOT NULL
                  AND oa.provider_email IS NOT NULL
                  AND LOWER(oa.provider_email) = LOWER(:provider_email)
                )
                OR oa.provider_user_id = :provider_user_id
              )
            """
        ),
        {
            "provider": provider,
            "provider_user_id": provider_user_id,
            "provider_email": provider_email,
        },
    ).fetchone()


def update_oauth_user_query(conn, user_id, oauth_user):
    conn.execute(
        text(
            """
            UPDATE users
            SET email = COALESCE(:email, email),
                display_name = COALESCE(:name, display_name),
                profile_image_url = COALESCE(:profile_image_url, profile_image_url),
                updated_at = NOW()
            WHERE user_id = :user_id
            """
        ),
        {
            "user_id": user_id,
            "email": oauth_user.get("email"),
            "name": oauth_user.get("name"),
            "profile_image_url": oauth_user.get("profile_image_url"),
        },
    )
    conn.execute(
        text(
            """
            UPDATE oauth_accounts
            SET provider_email = COALESCE(:provider_email, provider_email),
                provider_name = COALESCE(:provider_name, provider_name),
                last_used_at = NOW()
            WHERE user_id = :user_id AND provider = :provider
            """
        ),
        {
            "user_id": user_id,
            "provider": oauth_user["provider"],
            "provider_email": oauth_user.get("email"),
            "provider_name": oauth_user.get("name"),
        },
    )


def create_oauth_user_query(conn, oauth_user, role, status):
    created_user = conn.execute(
        text(
            """
            INSERT INTO users (
                email,
                display_name,
                profile_image_url,
                role,
                status,
                created_at,
                updated_at
            )
            VALUES (
                :email,
                :name,
                :profile_image_url,
                :role,
                :status,
                NOW(),
                NOW()
            )
            RETURNING user_id, email, display_name, profile_image_url, role, status
            """
        ),
        {
            "email": oauth_user.get("email"),
            "name": oauth_user.get("name"),
            "profile_image_url": oauth_user.get("profile_image_url"),
            "role": role,
            "status": status,
        },
    ).fetchone()
    user_id = created_user._mapping["user_id"] if hasattr(created_user, "_mapping") else created_user["user_id"]
    free_subscription = create_free_subscription_query(conn, user_id)
    if not free_subscription:
        raise RuntimeError("Active free plan is required to create a new user subscription.")
    conn.execute(
        text(
            """
            INSERT INTO oauth_accounts (
                user_id,
                provider,
                provider_user_id,
                provider_email,
                provider_name,
                linked_at,
                last_used_at
            )
            VALUES (
                :user_id,
                :provider,
                :provider_user_id,
                :provider_email,
                :provider_name,
                NOW(),
                NOW()
            )
            """
        ),
        {
            "user_id": user_id,
            "provider": oauth_user["provider"],
            "provider_user_id": oauth_user["provider_user_id"],
            "provider_email": oauth_user.get("email"),
            "provider_name": oauth_user.get("name"),
        },
    )

    # 초기 환영 크레딧 지급
    conn.execute(
        text(
            """
            INSERT INTO user_credit_balances (user_id, balance, free_balance, updated_at)
            VALUES (:user_id, 0, 10, NOW())
            """
        ),
        {"user_id": user_id},
    )

    conn.execute(
        text(
            """
            INSERT INTO credit_ledger (
                user_id,
                amount,
                balance_after,
                entry_type,
                source_type,
                source_id,
                description,
                created_at
            )
            VALUES (
                :user_id,
                10,
                0,
                'first_login',
                'oauth',
                :source_id,
                '가입 환영 크레딧 지급 (무료)',
                NOW()
            )
            """
        ),
        {"user_id": user_id, "source_id": str(user_id)},
    )

    return get_user_by_provider_query(
        conn,
        oauth_user["provider"],
        oauth_user["provider_user_id"],
        oauth_user.get("email"),
    )


def create_free_subscription_query(conn, user_id):
    return conn.execute(
        text(
            """
            INSERT INTO subscriptions (
                user_id,
                plan_id,
                status,
                started_at,
                renew_at,
                created_at,
                updated_at
            )
            SELECT
                :user_id,
                plan_id,
                'active',
                NOW(),
                NOW() + INTERVAL '30 days',
                NOW(),
                NOW()
            FROM plans
            WHERE LOWER(plan_code) = 'free'
              AND status = 'active'
            RETURNING subscription_id
            """
        ),
        {"user_id": user_id},
    ).fetchone()


def get_user_by_id_query(conn, user_id):
    return conn.execute(
        text(
            """
            SELECT
                u.user_id AS id,
                oa.provider,
                oa.provider_user_id,
                oa.provider_email,
                u.email,
                u.display_name AS name,
                u.profile_image_url,
                u.role,
                u.status
            FROM users u
            LEFT JOIN oauth_accounts oa ON oa.user_id = u.user_id
            WHERE u.user_id = :user_id
            """
        ),
        {"user_id": user_id},
    ).fetchone()


def mark_user_deleted_query(conn, user_id, status):
    return conn.execute(
        text(
            """
            UPDATE users
            SET status = :status,
                deleted_at = NOW(),
                updated_at = NOW()
            WHERE user_id = :user_id
            RETURNING user_id AS id, email, display_name AS name, profile_image_url, role, status
            """
        ),
        {"user_id": user_id, "status": status},
    ).fetchone()


def reactivate_user_query(conn, user_id):
    return conn.execute(
        text(
            """
            UPDATE users
            SET status = 'active',
                deleted_at = NULL,
                updated_at = NOW()
            WHERE user_id = :user_id
            RETURNING user_id AS id, email, display_name AS name, profile_image_url, role, status
            """
        ),
        {"user_id": user_id},
    ).fetchone()


def update_user_status_query(conn, user_id, status):
    return conn.execute(
        text(
            """
            UPDATE users
            SET status = :status,
                updated_at = NOW()
            WHERE user_id = :user_id
            RETURNING user_id AS id, email, display_name AS name, profile_image_url, role, status
            """
        ),
        {"user_id": user_id, "status": status},
    ).fetchone()


def get_user_consent_query(conn, user_id):
    return conn.execute(
        text(
            """
            SELECT is_agreed, version
            FROM user_consents
            WHERE user_id = :user_id AND consent_type = 'terms_and_privacy'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"user_id": user_id},
    ).fetchone()


def save_user_consent_query(conn, user_id, is_agreed, version, ip_address, user_agent):
    return conn.execute(
        text(
            """
            INSERT INTO user_consents (
                user_id, consent_type, is_agreed, version, source, ip_address, user_agent
            ) VALUES (
                :user_id, 'terms_and_privacy', :is_agreed, :version, 'signup_modal', :ip_address, :user_agent
            )
            RETURNING *
            """
        ),
        {
            "user_id": user_id,
            "is_agreed": is_agreed,
            "version": version,
            "ip_address": ip_address,
            "user_agent": user_agent,
        },
    ).fetchone()


def insert_login_history_query(conn, data):
    return conn.execute(
        text(
            """
            INSERT INTO user_login_histories (
                user_id,
                provider,
                provider_email,
                login_result,
                ip_address,
                user_agent,
                session_id
            ) VALUES (
                :user_id,
                :provider,
                :provider_email,
                :login_result,
                :ip_address,
                :user_agent,
                :session_id
            )
            """
        ),
        data
    )


def get_user_login_histories_query(conn, user_id, limit=5):
    return conn.execute(
        text(
            """
            SELECT 
                login_history_id,
                provider,
                login_result,
                ip_address,
                user_agent,
                session_id,
                logged_in_at
            FROM user_login_histories
            WHERE user_id = :user_id
            ORDER BY logged_in_at DESC
            LIMIT :limit
            """
        ),
        {"user_id": user_id, "limit": limit}
    ).fetchall()
