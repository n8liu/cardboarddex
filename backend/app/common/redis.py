import logging
from redis import Redis
from app.config import get_settings

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None


def get_redis() -> Redis | None:
    """Return a shared Redis client instance, or None if unavailable."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = Redis.from_url(get_settings().redis_url, decode_responses=True)
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "Redis unavailable; falling back to in-process local caches error=%s: %s",
                type(exc).__name__,
                exc,
            )
            _redis_client = None
    return _redis_client
