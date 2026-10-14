import logging
import time
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar

from redis import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


_SCHEDULED = ContextVar("scheduled_pricing_budget", default=None)
RESERVE = """
if ARGV[3] ~= '' and redis.call('get', KEYS[3]) ~= ARGV[3] then return -3 end
if tonumber(redis.call('get', KEYS[1]) or '0') >= tonumber(ARGV[1]) then return -1 end
if tonumber(ARGV[2]) > 0 and tonumber(redis.call('get', KEYS[2]) or '0') >= tonumber(ARGV[2]) then return -2 end
local n = redis.call('incr', KEYS[1]); redis.call('expire', KEYS[1], 90000)
if tonumber(ARGV[2]) > 0 then redis.call('incr', KEYS[2]); redis.call('expire', KEYS[2], 90000) end
return n
"""


@contextmanager
def scheduled_budget(provider, limit, lease_key, lease_token):
    token = _SCHEDULED.set((provider, limit, lease_key, lease_token))
    try:
        yield
    finally:
        _SCHEDULED.reset(token)


class ProviderRequestLimitExceeded(RuntimeError):
    pass


class DailyRequestLimiter:
    def __init__(
        self,
        redis_url: str,
        provider: str,
        limit: int,
        max_per_second: int = 8,
        now: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        redis_client: Redis | None = None,
    ) -> None:
        self.redis = redis_client or Redis.from_url(
            redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2,
        )
        self.provider = provider
        self.limit = limit
        self.max_per_second = max_per_second
        self.now = now
        self.sleep = sleep

    def acquire(self) -> None:
        current_time = self.now()
        day_bucket = int(current_time // 86400)
        daily_key = f"cardboarddex:{self.provider}:requests:{day_bucket}"

        # 1. Burst rate limiter (per-second bucket pacing)
        if self.max_per_second > 0:
            for _ in range(3):
                second_bucket = int(current_time)
                burst_key = f"cardboarddex:{self.provider}:burst:{second_bucket}"
                try:
                    burst_count = int(self.redis.incr(burst_key))
                    if burst_count == 1:
                        self.redis.expire(burst_key, 5)
                except RedisError as exc:
                    logger.error(
                        "Provider burst rate limiter failed provider=%s key=%s error=%s: %s",
                        self.provider,
                        burst_key,
                        type(exc).__name__,
                        exc,
                    )
                    raise

                if burst_count > self.max_per_second:
                    sleep_time = max(0.1, 1.0 - (current_time - second_bucket))
                    logger.warning(
                        "Provider burst limit pacing provider=%s count=%s max_per_sec=%s sleeping=%.2fs",
                        self.provider,
                        burst_count,
                        self.max_per_second,
                        sleep_time,
                    )
                    self.sleep(sleep_time)
                    current_time = self.now()
                else:
                    break

        # Reserve both allowances atomically immediately before each HTTP attempt.
        # A crash after reservation conservatively consumes that request allowance.
        day_bucket = int(self.now() // 86400)
        daily_key = f"cardboarddex:{self.provider}:requests:{day_bucket}"
        scheduled_key = f"cardboarddex:{self.provider}:scheduled_requests:{day_bucket}"
        budget = _SCHEDULED.get()
        sublimit, lease_key, lease_token = 0, daily_key, ""
        if budget is not None:
            provider, sublimit, lease_key, lease_token = budget
            if provider != self.provider:
                raise ProviderRequestLimitExceeded("Unexpected provider in scheduled request context")
        try:
            count = int(self.redis.eval(RESERVE, 3, daily_key, scheduled_key, lease_key,
                                        self.limit, sublimit, lease_token))
        except RedisError as exc:
            logger.error("Provider quota reservation failed provider=%s error=%s: %s",
                         self.provider, type(exc).__name__, exc)
            raise
        if count < 0:
            reason = {-1: "daily_limit", -2: "scheduled_limit", -3: "lease_expired"}[count]
            logger.warning("Provider request blocked provider=%s reason=%s", self.provider, reason)
            raise ProviderRequestLimitExceeded(f"{self.provider} request blocked: {reason}")
