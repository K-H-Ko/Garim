import os
from functools import lru_cache

from redis import Redis


DEFAULT_REDIS_URL = "redis://localhost:6379/0"


@lru_cache(maxsize=1)
def get_redis_client():
    """환경변수 REDIS_URL을 기준으로 Redis 연결 객체를 한 번만 생성해서 재사용합니다."""
    redis_url = os.getenv("REDIS_URL", DEFAULT_REDIS_URL)
    return Redis.from_url(redis_url, decode_responses=True)


def ping_redis():
    """Redis 서버에 ping을 보내 연결 가능 여부를 확인합니다."""
    return bool(get_redis_client().ping())
