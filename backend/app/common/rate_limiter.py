import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from app.common.redis import get_redis

logger = logging.getLogger(__name__)

# Fallback in-process storage with size limit to prevent memory exhaustion
_IN_MEMORY_RATE_LIMITS: OrderedDict[str, list[float]] = OrderedDict()
_MAX_IN_MEMORY_KEYS = 5000


def get_client_ip(request: Request) -> str:
    """Extract canonical client IP considering Cloudflare and proxy headers."""
    # 1. Cloudflare header
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip and cf_ip.strip():
        return cf_ip.strip()

    # 2. X-Forwarded-For (left-most IP is the original client)
    xff = request.headers.get("x-forwarded-for")
    if xff:
        client_ip = xff.split(",")[0].strip()
        if client_ip:
            return client_ip

    # 3. Direct socket address
    if request.client and request.client.host:
        return request.client.host

    return "127.0.0.1"


def _check_in_memory_rate_limit(key: str, max_requests: int, window_seconds: int) -> bool:
    """In-process sliding window rate limit fallback."""
    now = time.time()
    cutoff = now - window_seconds

    # Evict old keys if map exceeds max capacity
    while len(_IN_MEMORY_RATE_LIMITS) > _MAX_IN_MEMORY_KEYS:
        _IN_MEMORY_RATE_LIMITS.popitem(last=False)

    timestamps = _IN_MEMORY_RATE_LIMITS.get(key, [])
    # Filter timestamps within active window
    active_timestamps = [t for t in timestamps if t > cutoff]

    if len(active_timestamps) >= max_requests:
        _IN_MEMORY_RATE_LIMITS[key] = active_timestamps
        _IN_MEMORY_RATE_LIMITS.move_to_end(key)
        return False

    active_timestamps.append(now)
    _IN_MEMORY_RATE_LIMITS[key] = active_timestamps
    _IN_MEMORY_RATE_LIMITS.move_to_end(key)
    return True


def check_rate_limit(
    client_ip: str,
    bucket: str = "default",
    max_requests: int = 120,
    window_seconds: int = 60,
) -> tuple[bool, int]:
    """
    Check if a client IP has exceeded the allowed request velocity.
    Returns (is_allowed, retry_after_seconds).
    """
    now = int(time.time())
    window_bucket = now // window_seconds
    redis_key = f"cardboarddex:rl:{bucket}:{client_ip}:{window_bucket}"
    retry_after = max(1, window_seconds - (now % window_seconds))

    r = get_redis()
    if r is not None:
        try:
            current = r.incr(redis_key)
            if current == 1:
                r.expire(redis_key, window_seconds + 5)
            if current > max_requests:
                return False, retry_after
            return True, 0
        except (RedisError, Exception) as exc:
            logger.warning(
                "Redis rate limit check failed bucket=%s ip=%s error=%s: %s; falling back to in-memory",
                bucket,
                client_ip,
                type(exc).__name__,
                exc,
            )

    # Fallback in-process sliding window
    mem_key = f"{bucket}:{client_ip}"
    allowed = _check_in_memory_rate_limit(mem_key, max_requests, window_seconds)
    return allowed, (retry_after if not allowed else 0)


def rate_limit(
    max_requests: int = 120,
    window_seconds: int = 60,
    bucket: str = "default",
) -> Callable[[Request], None]:
    """FastAPI route dependency to enforce rate limiting on specific endpoints."""

    def dependency(request: Request) -> None:
        client_ip = get_client_ip(request)
        allowed, retry_after = check_rate_limit(
            client_ip=client_ip,
            bucket=bucket,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )
        if not allowed:
            logger.warning("Rate limit exceeded for client_ip=%s on bucket=%s", client_ip, bucket)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down and try again later.",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency
