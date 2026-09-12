import logging
import time
from collections.abc import Callable

from redis import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


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
        self.redis = redis_client or Redis.from_url(redis_url, decode_responses=True)
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
                    break

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

        # 2. Daily safety ceiling limiter
        try:
            count = int(self.redis.incr(daily_key))
            if count == 1:
                self.redis.expire(daily_key, 90000)
        except RedisError as exc:
            logger.error(
                "Provider daily rate limiter failed provider=%s key=%s limit=%s error=%s: %s",
                self.provider,
                daily_key,
                self.limit,
                type(exc).__name__,
                exc,
            )
            raise
        if count > self.limit:
            error = ProviderRequestLimitExceeded(
                f"{self.provider} daily safety limit reached ({self.limit} requests)"
            )
            logger.error(
                "Provider request blocked provider=%s key=%s count=%s limit=%s error=%s: %s",
                self.provider,
                daily_key,
                count,
                self.limit,
                type(error).__name__,
                error,
            )
            raise error
