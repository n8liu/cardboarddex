"""Worker-published snapshots for the movers, sealed and grading-profit pages.

Each snapshot is rebuilt at most once every 12 hours. Beat checks every 15 minutes
and rebuilds only a snapshot that is due or missing (the cache Redis evicts), so a
lost snapshot comes back within minutes without querying more often. Public reads
never run the full query; they only filter and paginate the published rows.
"""
import json
import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.common.redis import get_redis
from app.common.response_cache import _RELEASE
from app.config import get_settings
from app.database import SessionLocal

logger = logging.getLogger(__name__)

REFRESH_SECONDS = 12 * 3600
# A failed rebuild keeps serving the previous snapshot for another day.
MAX_SECONDS = 36 * 3600
LEASE_SECONDS = 600
# Worker-only bound; public SQL keeps its five-second deadline.
STATEMENT_TIMEOUT = "120000ms"
# KEYS: lock, part keys. ARGV: token, one value per part, TTL.
_PUBLISH_PARTS = """if redis.call('get',KEYS[1]) ~= ARGV[1] then return 0 end
for i = 2, #KEYS do redis.call('set', KEYS[i], ARGV[i], 'EX', ARGV[#KEYS + 1]) end
redis.call('del', KEYS[1]); return 1"""


def part_key(name: str, part: str = "all") -> str:
    source_key = "ppt" if get_settings().ppt_primary_enabled else "legacy"
    return f"cardboarddex:{source_key}:{name}-snapshot:v1:{part}"


def is_due(redis, name: str, parts: list[str]) -> bool:
    """Due when any part is missing or the oldest part was published 12+ hours ago."""
    keys = [part_key(name, part) for part in parts]
    ttls = [redis.ttl(key) for key in keys]
    return any(ttl is None or ttl < 0 for ttl in ttls) or min(ttls) <= MAX_SECONDS - REFRESH_SECONDS


def refresh(name: str, parts: list[str], build: Callable[[Session, datetime], dict[str, str]], *, force=False) -> bool:
    """Build and publish every part together under one lease; False when skipped or failed."""
    started = time.monotonic()
    redis = get_redis()
    if redis is None:
        logger.warning("Snapshot refresh unavailable name=%s: Redis client unavailable", name)
        return False
    lock, token = part_key(name, "lock"), uuid.uuid4().hex
    acquired = False
    try:
        if not force and not is_due(redis, name, parts):
            return False
        acquired = bool(redis.set(lock, token, nx=True, ex=LEASE_SECONDS))
        if not acquired:
            return False
        # Another publisher may have finished between the due check and this lease.
        if not force and not is_due(redis, name, parts):
            return False
        now = datetime.now(UTC)
        with SessionLocal() as db:
            if db.get_bind().dialect.name == "postgresql":
                db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
                db.execute(text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'"))
            values = build(db, now)
        raws = [values[part] for part in parts]
        published = bool(redis.eval(_PUBLISH_PARTS, 1 + len(parts), lock, *[part_key(name, p) for p in parts],
                                    token, *raws, MAX_SECONDS))
        logger.info("Snapshot refresh name=%s published=%s duration_ms=%.1f bytes=%d", name, published,
                    (time.monotonic() - started) * 1000, sum(len(raw.encode()) for raw in raws))
        return published
    except Exception as exc:
        logger.exception("Snapshot refresh failed name=%s error=%s: %s", name, type(exc).__name__, exc)
        return False
    finally:
        if acquired:
            try:
                redis.eval(_RELEASE, 1, lock, token)
            except Exception as exc:
                logger.warning("Snapshot lock release failed name=%s error=%s: %s", name, type(exc).__name__, exc)


def unavailable() -> HTTPException:
    return HTTPException(503, "Results are being prepared; try again shortly",
                         headers={"Retry-After": "60", "Cache-Control": "no-store"})


def _redis_unavailable():
    if get_settings().market_snapshots_on_demand_fallback:
        return None
    raise unavailable()


def read(name: str, part: str = "all") -> dict | None:
    """Read stored data; only an explicit local-development flag permits SQL fallback."""
    redis = get_redis()
    if redis is None:
        return _redis_unavailable()
    try:
        raw = redis.get(part_key(name, part))
    except Exception as exc:
        logger.warning("Snapshot read failed name=%s error=%s: %s", name, type(exc).__name__, exc)
        return _redis_unavailable()
    if raw:
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("snapshot must be an object")
            age = (datetime.now(UTC) - datetime.fromisoformat(data["updated_at"])).total_seconds()
            if age < 0 or age >= MAX_SECONDS:
                raise ValueError(f"snapshot age out of bounds: {age}")
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Snapshot invalid name=%s error=%s: %s", name, type(exc).__name__, exc)
        else:
            if age > REFRESH_SECONDS + 3600:
                logger.warning("Snapshot stale name=%s age_seconds=%.0f; is the worker running?", name, age)
            return data
    raise unavailable()


def on_demand_session(db: Session) -> Session:
    """Without Redis the route computes in-request, under the public five-second deadline."""
    if not get_settings().market_snapshots_on_demand_fallback:
        raise unavailable()
    logger.warning("Local market snapshot fallback: computing on request")
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL statement_timeout = '5000ms'"))
    return db


def cache_headers(response, updated_at: datetime) -> None:
    age = max(0, (datetime.now(UTC) - updated_at).total_seconds())
    fresh = max(0, min(300, int(REFRESH_SECONDS - age)))
    response.headers["Cache-Control"] = f"public, max-age=0, s-maxage={fresh if fresh else 10}"
    response.headers["X-Cache-Status"] = "hit" if fresh else "stale"
    response.headers["X-Cache-Generated-At"] = updated_at.isoformat()
