import json
import os

from core.redis import get_redis_client, ping_redis


DEFAULT_SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
DEFAULT_OAUTH_STATE_TTL_SECONDS = 60 * 5
DEFAULT_DASHBOARD_CACHE_TTL_SECONDS = 10
DEFAULT_PROGRESS_TTL_SECONDS = 60 * 60


def get_ttl(env_name, default_value):
    """TTL 환경변수를 초 단위 정수로 읽고, 값이 없거나 잘못되면 기본값을 반환합니다."""
    try:
        value = int(os.getenv(env_name, str(default_value)))
    except ValueError:
        return default_value
    return value if value > 0 else default_value


def build_key(namespace, key):
    """Redis key 충돌을 줄이기 위해 namespace:key 형식의 키를 만듭니다."""
    return f"{namespace}:{key}"


def set_json(namespace, key, value, ttl_seconds):
    """dict/list 같은 데이터를 JSON 문자열로 변환해 TTL과 함께 Redis에 저장합니다."""
    redis_key = build_key(namespace, key)
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    get_redis_client().setex(redis_key, ttl_seconds, payload)
    return redis_key


def get_json(namespace, key):
    """Redis에 저장된 JSON 문자열을 읽어 Python 객체로 변환합니다."""
    payload = get_redis_client().get(build_key(namespace, key))
    if payload is None:
        return None
    return json.loads(payload)


def delete_key(namespace, key):
    """namespace:key 형식의 Redis 값을 삭제하고 삭제 여부를 bool로 반환합니다."""
    return bool(get_redis_client().delete(build_key(namespace, key)))


def save_oauth_state(state, data):
    """OAuth 로그인 과정에서 CSRF 방지용 state와 부가 데이터를 짧게 저장합니다."""
    ttl = get_ttl("REDIS_OAUTH_STATE_TTL_SECONDS", DEFAULT_OAUTH_STATE_TTL_SECONDS)
    return set_json("oauth_state", state, data, ttl)


def get_oauth_state(state):
    """저장된 OAuth state 데이터를 조회합니다."""
    return get_json("oauth_state", state)


def delete_oauth_state(state):
    """사용이 끝난 OAuth state 데이터를 삭제합니다."""
    return delete_key("oauth_state", state)


def consume_oauth_state(state):
    """OAuth state를 한 번 조회한 뒤 즉시 삭제해 재사용을 막습니다."""
    data = get_oauth_state(state)
    delete_oauth_state(state)
    return data


def save_session(session_id, data):
    """로그인 세션 데이터를 Redis에 저장합니다."""
    ttl = get_ttl("REDIS_SESSION_TTL_SECONDS", DEFAULT_SESSION_TTL_SECONDS)
    return set_json("auth:session", session_id, data, ttl)


def get_session(session_id):
    """session_id에 해당하는 로그인 세션 데이터를 조회합니다."""
    return get_json("auth:session", session_id)


def delete_session(session_id):
    """로그아웃 또는 만료 처리 시 로그인 세션 데이터를 삭제합니다."""
    return delete_key("auth:session", session_id)


def delete_user_sessions(user_id):
    """Delete every Redis auth session belonging to a user."""
    client = get_redis_client()
    deleted_count = 0
    user_id = str(user_id)
    for redis_key in list(client.scan_iter(match="auth:session:*")):
        payload = client.get(redis_key)
        if payload is None:
            continue
        try:
            session = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if str(session.get("user_id")) == user_id:
            deleted_count += int(client.delete(redis_key))
    return deleted_count


def set_dashboard_cache(key, data):
    """대시보드 통계처럼 짧게 재사용할 데이터를 10초 기본 TTL로 캐싱합니다."""
    ttl = get_ttl("REDIS_DASHBOARD_CACHE_TTL_SECONDS", DEFAULT_DASHBOARD_CACHE_TTL_SECONDS)
    return set_json("dashboard", key, data, ttl)


def get_dashboard_cache(key):
    """대시보드 통계 캐시를 조회합니다."""
    return get_json("dashboard", key)


def delete_dashboard_cache(key):
    """대시보드 통계 캐시를 강제로 삭제합니다."""
    return delete_key("dashboard", key)


def set_progress(job_id, data):
    """분석/처리 작업의 진행률 데이터를 Redis에 임시 저장합니다."""
    ttl = get_ttl("REDIS_PROGRESS_TTL_SECONDS", DEFAULT_PROGRESS_TTL_SECONDS)
    return set_json("progress", job_id, data, ttl)


def get_progress(job_id):
    """job_id에 해당하는 진행률 캐시를 조회합니다."""
    return get_json("progress", job_id)


def delete_progress(job_id):
    """작업 완료 또는 취소 후 진행률 캐시를 삭제합니다."""
    return delete_key("progress", job_id)


def redis_healthcheck():
    """헬스체크에서 사용할 Redis 연결 상태를 확인합니다."""
    return ping_redis()
