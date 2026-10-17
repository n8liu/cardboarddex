"""Bounded PPT requests. Credits and weighted minute usage are different units."""
import logging
import math
import time
import uuid
from dataclasses import dataclass
import httpx
from app.common.redis import get_durable_redis
from app.config import get_settings

logger = logging.getLogger(__name__)
PROVIDER = "pokemonpricetracker"
BASE_URL = "https://www.pokemonpricetracker.com/api/v2"
LANES = {"priority": 4500, "rotation": 13000, "graded": 500, "discovery": 1500, "retry": 500}
PREFIX = "cardboarddex:ppt:v1"

# One atomic reservation covers all workers, including manual tools. A lost response
# stays spent. Redis uses a non-evicting durable store; missing connectivity fails closed.
RESERVE = """
if redis.call('exists', KEYS[4]) == 1 then return -4 end
if redis.call('exists', KEYS[5]) == 1 then return -5 end
redis.call('zremrangebyscore', KEYS[3], '-inf', ARGV[1] - 60)
if redis.call('zcard', KEYS[3]) + tonumber(ARGV[3]) > tonumber(ARGV[5]) then return -3 end
local spent = tonumber(redis.call('get', KEYS[1]) or '0')
if spent + tonumber(ARGV[2]) > tonumber(ARGV[4]) then return -1 end
local lane = tonumber(redis.call('get', KEYS[2]) or '0')
local bonus = tonumber(ARGV[8])
if bonus > 0 and tonumber(redis.call('get', KEYS[6]) or '0') + bonus > 500 then return -6 end
if lane + tonumber(ARGV[2]) - bonus > tonumber(ARGV[6]) then return -2 end
redis.call('incrby', KEYS[1], ARGV[2]); redis.call('expire', KEYS[1], 172800)
redis.call('incrby', KEYS[6], bonus); redis.call('expire', KEYS[6], 172800)
redis.call('incrby', KEYS[2], tonumber(ARGV[2]) - bonus); redis.call('expire', KEYS[2], 172800)
for i=1,tonumber(ARGV[3]) do redis.call('zadd', KEYS[3], ARGV[1], ARGV[7]..':'..i) end
redis.call('expire', KEYS[3], 120)
redis.call('set', KEYS[5], ARGV[7], 'EX', 45)
return spent + tonumber(ARGV[2])
"""
RECONCILE = """
local delta = tonumber(ARGV[1]) - tonumber(ARGV[2])
redis.call('incrby', KEYS[1], delta); redis.call('incrby', KEYS[2], delta)
if tonumber(ARGV[3]) >= 0 then
 local minimum = tonumber(ARGV[4]) - tonumber(ARGV[3])
 if tonumber(redis.call('get', KEYS[1]) or '0') < minimum then redis.call('set', KEYS[1], minimum, 'EX', 172800) end
end
"""
RELEASE = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0"
COOLDOWN = """
local ttl = redis.call('ttl', KEYS[1])
if ttl < tonumber(ARGV[1]) then redis.call('set', KEYS[1], ARGV[2], 'EX', ARGV[1]) end
"""


class PPTBlocked(RuntimeError):
    """Normal scheduler yield: no provider request was attempted."""


@dataclass(frozen=True)
class Reservation:
    day: int
    lane: str
    cost: int
    token: str
    bonus: int = 0


class PPTQuota:
    def __init__(self, redis=None, now=time.time):
        self.redis = redis if redis is not None else get_durable_redis()
        self.now = now
        self.settings = get_settings()

    def reserve(self, cost, weight, lane, bonus=0):
        if lane not in LANES or cost < 1 or weight < 1 or bonus not in (0, 1) or bonus >= cost:
            raise ValueError("Invalid PPT reservation")
        now = self.now()
        if now % 86400 >= 86370:
            raise PPTBlocked("utc_rollover")
        day = int(now // 86400)
        token = uuid.uuid4().hex
        # Retry allowance stays reserved until the final two UTC hours. Then
        # overdue queues may borrow unused lane capacity without crossing the cap.
        late = now % 86400 >= 22 * 3600
        cap = self.settings.ppt_daily_credit_limit
        if not late and lane != "retry":
            cap = max(0, cap - min(500, cap // 40))
        lane_cap = self.settings.ppt_daily_credit_limit if late else LANES[lane]
        result = self.redis.eval(RESERVE, 6, f"{PREFIX}:credits:{day}",
            f"{PREFIX}:lane:{day}:{lane}", f"{PREFIX}:minute", f"{PREFIX}:cooldown", f"{PREFIX}:flight", f"{PREFIX}:lane:{day}:graded",
            now, cost, weight, cap, self.settings.ppt_minute_weight_limit, lane_cap, token, bonus)
        if int(result) < 0:
            reason = {-1: "daily", -2: "lane", -3: "minute", -4: "cooldown", -5: "in_flight", -6: "graded_lane"}[int(result)]
            raise PPTBlocked(reason)
        return Reservation(day, lane, cost, token, bonus)

    def finish(self, reservation, headers=None):
        try:
            if headers is not None:
                consumed = headers.get("X-API-Calls-Consumed")
                remaining = headers.get("X-RateLimit-Daily-Remaining")
                # Never use Purchased-Remaining or Total-Remaining: those allow paid overage.
                actual = int(consumed) if consumed is not None else reservation.cost
                if reservation.bonus:
                    actual = max(reservation.bonus, actual)
                daily = int(remaining) if remaining is not None else -1
                if actual < 0 or daily < -1:
                    raise ValueError("Invalid PPT quota headers")
                self.redis.eval(RECONCILE, 2, f"{PREFIX}:credits:{reservation.day}",
                    f"{PREFIX}:lane:{reservation.day}:{reservation.lane}", actual, reservation.cost,
                    daily, 20000)
                minute_remaining = headers.get("X-RateLimit-Minute-Remaining")
                if minute_remaining is not None and int(minute_remaining) < 5:
                    self.cooldown(60, "provider_minute_remaining")
        except (ValueError, TypeError) as exc:
            logger.error("PPT invalid quota headers: %s: %s", type(exc).__name__, exc)
            self.cooldown(86400, "invalid_quota_headers")
            raise
        finally:
            self.redis.eval(RELEASE, 1, f"{PREFIX}:flight", reservation.token)

    def cooldown(self, seconds, reason):
        self.redis.eval(COOLDOWN, 1, f"{PREFIX}:cooldown", max(1, math.ceil(seconds)), reason)


class PPTClient:
    def __init__(self, quota=None, client=None):
        self.quota = quota or PPTQuota()
        self.client = client or httpx.Client(timeout=20, follow_redirects=False)
        self.key = get_settings().ppt_api_key

    def close(self):
        self.client.close()

    def request(self, path, *, lane="rotation", bonus_graded=False, **params):
        if path not in {"cards", "sealed-products", "sets"}:
            raise ValueError("Unsupported PPT resource")
        if not self.key:
            raise PPTBlocked("missing_api_key")
        allowed = {"language", "limit", "offset", "tcgPlayerId", "setId", "includeHistory", "includeEbay"}
        if set(params) - allowed:
            raise ValueError("Unsupported PPT request parameters")
        if path == "sealed-products" and not (params.get("tcgPlayerId") or params.get("setId")):
            raise ValueError("Sealed queries require an exact product or set filter")
        if params.get("language", "english") not in {"english", "japanese"}:
            raise ValueError("Unsupported PPT language")
        limit = int(params.get("limit", 1))
        if not 1 <= limit <= (100 if path == "sets" else 25):
            raise ValueError("PPT page exceeds bounded ingestion size")
        if params.get("fetchAllInSet"):
            raise ValueError("Unbounded set fetches are disabled")
        params["limit"] = limit
        history = bool(params.get("includeHistory"))
        graded = bool(params.get("includeEbay"))
        if path != "cards" and graded:
            raise ValueError("Graded sales are only available for cards")
        if history or graded:
            params["days"] = 180
            if path == "cards":
                params["maxDataPoints"] = 180
        cost = 1 if path == "sets" else limit * (1 + history + graded)
        weight = 1 if path == "sets" else min(30, math.ceil(limit / 10))
        reservation = self.quota.reserve(cost, weight, lane, bonus=int(bonus_graded))
        response = None
        try:
            response = self.client.get(f"{BASE_URL}/{path}", params={k: str(v).lower() if isinstance(v, bool) else v for k, v in params.items()},
                headers={"Authorization": f"Bearer {self.key}"})
            if response.status_code in (401, 403):
                self.quota.cooldown(86400, "authentication")
            if response.status_code == 429:
                self.quota.cooldown(60, "provider_429")
                body = response.json()
                seconds = response.headers.get("Retry-After") or body.get("retryAfter") or 60
                if body.get("limitType") == "daily":
                    seconds = 86400 - self.quota.now() % 86400
                self.quota.cooldown(float(seconds), "provider_429")
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data")
            if not isinstance(data, (dict, list)):
                raise ValueError("PPT response lacks object/list data")
            rows = data if isinstance(data, list) else [data]
            if len(rows) > limit or any(not isinstance(row, dict) for row in rows):
                raise ValueError("PPT response exceeded requested page or contains invalid rows")
            return rows
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.error("PPT request failed resource=%s error=%s: %s", path, type(exc).__name__, exc)
            raise
        finally:
            self.quota.finish(reservation, response.headers if response is not None else None)
