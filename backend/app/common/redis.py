import logging
from redis import Redis
from app.config import get_settings

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None
_durable_redis_client: Redis | None = None


def get_durable_redis() -> Redis:
    """Broker, quotas and checkpoints must never use the evicting cache."""
    global _durable_redis_client
    if _durable_redis_client is None:
        settings = get_settings()
        _durable_redis_client = Redis.from_url(
            settings.redis_url, decode_responses=True,
            socket_connect_timeout=settings.redis_socket_timeout,
            socket_timeout=settings.redis_socket_timeout,
        )
    return _durable_redis_client


def get_redis() -> Redis | None:
    """Return a shared Redis client instance, or None if unavailable."""
    global _redis_client
    if _redis_client is None:
        try:
            settings = get_settings()
            _redis_client = Redis.from_url(
                settings.cache_redis_url or settings.redis_url, decode_responses=True,
                socket_connect_timeout=settings.redis_socket_timeout,
                socket_timeout=settings.redis_socket_timeout,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "Redis unavailable; falling back to in-process local caches error=%s: %s",
                type(exc).__name__,
                exc,
            )
            _redis_client = None
    return _redis_client

# Created lazily on the running API loop; never shared with Celery/sync clients.
_async_redis_client = None


def get_async_redis():
    from redis.asyncio import Redis as AsyncRedis
    global _async_redis_client
    if _async_redis_client is None:
        settings = get_settings()
        _async_redis_client = AsyncRedis.from_url(
            settings.cache_redis_url or settings.redis_url, decode_responses=True,
            socket_connect_timeout=settings.redis_socket_timeout,
            socket_timeout=settings.redis_socket_timeout,
        )
    return _async_redis_client


async def close_async_redis():
    global _async_redis_client
    client, _async_redis_client = _async_redis_client, None
    if client is not None:
        await client.aclose()
