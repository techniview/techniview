import redis

from .config import settings


def redis_conn():
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
        socket_connect_timeout=2,
        decode_responses=True,
    )
