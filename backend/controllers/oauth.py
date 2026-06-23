import logging
from urllib.parse import urlparse

from fastapi import Body, Cookie, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from services import auth, oauth, redis_store, users

logger = logging.getLogger(__name__)


def start_oauth(
    provider: str,
    reregister: bool = Query(False),
    next: str | None = Query(default=None),
):
    try:
        authorization_url = oauth.build_authorization_url(
            provider,
            force_consent=reregister,
            next_path=safe_frontend_path(next),
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="지원하지 않는 OAuth 제공자입니다.") from exc
    except oauth.OAuthConfigError as exc:
        return JSONResponse({"message": str(exc)}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    return RedirectResponse(authorization_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


def oauth_callback(
    request: Request,
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")

    if error:
        logger.warning("[oauth] provider=%s ip=%s provider_error=%s", provider, ip, error)
        return redirect_after_login_failure()
    if not code or not state:
        logger.warning("[oauth] provider=%s ip=%s error=missing_code_or_state", provider, ip)
        return redirect_after_login_failure()

    try:
        oauth_user, state_data, provider_token = oauth.exchange_code_for_user(provider, code, state)
        if state_data.get("reregister"):
            user = users.reactivate_or_create_user(oauth_user)
            logger.info("[oauth] reregister provider=%s email=%s ip=%s", provider, oauth_user.get("email"), ip)
        else:
            user = users.get_or_create_oauth_user(oauth_user)
            if user.get("status") == users.DELETED:
                logger.info("[oauth] deleted_user provider=%s email=%s ip=%s → redirect reregister", provider, oauth_user.get("email"), ip)
                if provider == "kakao":
                    oauth.unlink_kakao_with_user_token(provider_token)
                elif provider == "naver":
                    oauth.unlink_naver_with_user_token(provider_token)
                return redirect_to_reregister(provider)
        token_pair = auth.create_login_session(
            user,
            user_agent=ua,
            ip_address=ip,
        )
        
        # auth.create_login_session returns (access_token, refresh_token, garim_auth)
        # Session ID is typically inside garim_auth token or we can just pass None and it won't be recorded
        users.record_login_history(
            user_id=user["id"],
            provider=provider,
            provider_email=oauth_user.get("email"),
            login_result="success",
            ip_address=ip,
            user_agent=ua,
            session_id=None
        )
    except (oauth.OAuthStateError, oauth.OAuthExchangeError) as exc:
        logger.error("[oauth] provider=%s ip=%s error=%s", provider, ip, exc, exc_info=True)
        return redirect_after_login_failure()
    except (KeyError, oauth.OAuthConfigError) as exc:
        logger.error("[oauth] provider=%s ip=%s config_error=%s", provider, ip, exc, exc_info=True)
        return redirect_after_login_failure()
    except HTTPException:
        logger.warning("[oauth] provider=%s email=%s ip=%s error=account_inactive", provider, oauth_user.get("email"), ip)
        return redirect_after_login_failure()
    except Exception as exc:
        logger.error("[oauth] provider=%s ip=%s unhandled_error=%s", provider, ip, exc, exc_info=True)
        return redirect_after_login_failure()

    role = user.get("role", users.USER)
    logger.info("[oauth] login_success provider=%s user_id=%s role=%s ip=%s", provider, user.get("id"), role, ip)
    response = redirect_to_frontend(role=role, next_path=state_data.get("next_path"))
    auth.set_auth_cookies(response, token_pair)
    return response


def get_me(access_token: str | None = Cookie(default=None)):
    user = auth.authenticate_access_token(access_token)
    return {"authenticated": True, "user": user}


def get_status(access_token: str | None = Cookie(default=None)):
    try:
        user = auth.authenticate_access_token(access_token)
    except HTTPException:
        return {"authenticated": False, "user": None}
    return {"authenticated": True, "user": user}


def refresh(refresh_token: str | None = Cookie(default=None)):
    token_pair = auth.refresh_login_session(refresh_token)
    response = JSONResponse({"authenticated": True})
    auth.set_auth_cookies(response, token_pair)
    return response


def logout(
    access_token: str | None = Cookie(default=None),
    refresh_token: str | None = Cookie(default=None),
    garim_auth: str | None = Cookie(default=None),
):
    auth.delete_session_from_tokens(access_token, refresh_token, garim_auth)
    response = JSONResponse({"authenticated": False})
    auth.delete_auth_cookies(response)
    return response


def delete_me(access_token: str | None = Cookie(default=None)):
    current_user = auth.authenticate_access_token(access_token)
    users.mark_user_deleted(current_user["id"])
    redis_store.delete_user_sessions(current_user["id"])
    response = JSONResponse({"deleted": True})
    auth.delete_auth_cookies(response)
    return response


def update_user_status(user_id: int, payload: dict = Body(...)):
    status_value = payload.get("status", "")
    try:
        user = users.update_user_status(user_id, status_value)
    except users.UserStatusError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user["status"] != users.ACTIVE:
        redis_store.delete_user_sessions(user_id)
    return {"user": user}


def delete_session(session_id: str):
    redis_store.delete_session(session_id)
    return {"deleted": True}


def delete_sessions(access_token: str | None = Cookie(default=None)):
    current_user = auth.authenticate_access_token(access_token)
    redis_store.delete_user_sessions(current_user["id"])
    response = JSONResponse({"deleted": True})
    auth.delete_auth_cookies(response)
    return response


def safe_frontend_path(path: str | None) -> str:
    if not path:
        return "/"
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc:
        return "/"
    if not path.startswith("/") or path.startswith("//"):
        return "/"
    return path


def redirect_to_frontend(role=None, next_path=None):
    base_url = oauth.get_frontend_base_url()
    path = safe_frontend_path(next_path)
    return RedirectResponse(f"{base_url}{path}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


def redirect_after_login_failure():
    return redirect_to_frontend(next_path="/")


def redirect_to_reregister(provider):
    base_url = oauth.get_frontend_base_url()
    return RedirectResponse(
        f"{base_url}/login?reregister=true&provider={provider}",
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )


def get_consents(access_token: str | None = Cookie(default=None)):
    current_user = auth.authenticate_access_token(access_token)
    consent = users.get_user_consent(current_user["id"])
    if consent and consent["is_agreed"]:
        return {"consented": True, "version": consent["version"]}
    return {"consented": False}


def save_consents(
    request: Request,
    is_agreed: bool = Body(...),
    version: str = Body(...),
    access_token: str | None = Cookie(default=None)
):
    current_user = auth.authenticate_access_token(access_token)
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    consent = users.save_user_consent(
        current_user["id"],
        is_agreed,
        version,
        ip_address=ip,
        user_agent=ua,
    )
    return {"success": True, "consent": consent}
