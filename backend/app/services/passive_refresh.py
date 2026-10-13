"""Bounded, popularity-aware selection for scheduled provider collection."""
import logging
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from redis.exceptions import RedisError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.redis import get_durable_redis, get_redis
from app.config import get_settings
from app.models import Card, ProviderCardState

logger = logging.getLogger(__name__)
PREFIX = "cardboarddex:passive:v1"
RELEASE = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"


def record_card_interest(redis, card_id: str, now: float | None = None) -> None:
    """Two bounded daily buckets; no extra connection or provider work on page views."""
    day = int((time.time() if now is None else now) // 86400)
    key = f"{PREFIX}:interest:{day}"
    pipe = redis.pipeline(transaction=True)
    pipe.zincrby(key, 1, card_id)
    pipe.zremrangebyrank(key, 0, -2001)
    pipe.expire(key, 172800)
    pipe.execute()


def popular_card_ids(now: float) -> list[str]:
    redis = get_redis()
    if redis is None:
        return []
    scores: dict[str, float] = {}
    try:
        day = int(now // 86400)
        for bucket in (day, day - 1):
            for member, score in redis.zrevrange(f"{PREFIX}:interest:{bucket}", 0, 1999, withscores=True):
                card_id = member.decode() if isinstance(member, bytes) else member
                scores[card_id] = scores.get(card_id, 0) + score
    except RedisError as exc:
        logger.warning("Passive popularity unavailable error=%s: %s", type(exc).__name__, exc)
        return []
    return sorted(scores, key=lambda card_id: (-scores[card_id], card_id))[:get_settings().passive_popular_card_count]


def select_due_cards(session: Session, provider: str, popular: list[str], now: datetime,
                     limit: int, attempts) -> list[str]:
    settings = get_settings()
    latest = (select(ProviderCardState.card_id, func.max(ProviderCardState.last_synced_at).label("synced"))
              .where(ProviderCardState.provider == provider)
              .group_by(ProviderCardState.card_id).subquery())
    base = (select(Card.id).outerjoin(latest, latest.c.card_id == Card.id)
            .where(Card.name.not_ilike("%code card%")))
    if provider == "tcgapi":
        base = base.where(Card.number.is_not(None), Card.number != "None")
    selected: list[str] = []

    def choose(hot: bool, count: int) -> None:
        if count <= 0:
            return
        hours = settings.passive_popular_refresh_hours if hot else settings.passive_catalog_refresh_hours
        cutoff = now - timedelta(hours=hours)
        stmt = base.where(or_(latest.c.synced.is_(None), latest.c.synced <= cutoff))
        stmt = stmt.where(Card.id.in_(popular) if hot else Card.id.not_in(popular))
        cooling = attempts.zrangebyscore(f"{PREFIX}:attempts:{provider}", f"({cutoff.timestamp()}", "+inf")
        if cooling:
            stmt = stmt.where(Card.id.not_in(cooling))
        selected.extend(session.scalars(stmt.order_by(latest.c.synced.asc().nullsfirst(), Card.id).limit(count)))

    # At least one slot remains for the long tail, even when popularity is busy.
    choose(True, min(settings.passive_popular_batch_size, max(0, limit - 1)))
    choose(False, limit - len(selected))
    return selected


def run_scheduled_collection(session: Session, provider: str, collect) -> dict:
    """Fail closed without durable Redis; one scheduled provider batch at a time."""
    settings = get_settings()
    if not settings.passive_refresh_enabled:
        return {"skipped": "disabled"}
    redis = get_durable_redis()
    token = uuid4().hex
    lock = f"{PREFIX}:batch"
    acquired = False
    try:
        # Longer than the scheduled Celery task's 840-second hard time limit.
        acquired = bool(redis.set(lock, token, nx=True, ex=900))
        if not acquired:
            return {"skipped": "busy"}
        now = datetime.now(UTC)
        daily_limit = getattr(settings, f"{provider}_daily_request_limit")
        used = int(redis.get(f"cardboarddex:{provider}:requests:{int(now.timestamp() // 86400)}") or 0)
        if used >= daily_limit:
            return {"skipped": "daily_limit"}
        ids = select_due_cards(session, provider, popular_card_ids(now.timestamp()), now,
                               settings.price_collection_card_limit, redis)
        if not ids:
            return {"cards": 0}
        pipe = redis.pipeline(transaction=True)
        attempt_key = f"{PREFIX}:attempts:{provider}"
        retention = max(settings.passive_catalog_refresh_hours, settings.passive_popular_refresh_hours) * 3600
        pipe.zremrangebyscore(attempt_key, "-inf", now.timestamp() - retention)
        pipe.zadd(attempt_key, {card_id: now.timestamp() for card_id in ids})
        pipe.expire(attempt_key, retention)
        pipe.execute()
        result = collect(session, card_ids=ids)
        logger.info("Passive refresh provider=%s selected=%s result=%s", provider, ids, result)
        return result
    except RedisError as exc:
        logger.error("Passive refresh stopped provider=%s error=%s: %s", provider, type(exc).__name__, exc)
        return {"skipped": "redis_unavailable"}
    finally:
        if acquired:
            try:
                redis.eval(RELEASE, 1, lock, token)
            except RedisError as exc:
                logger.error("Passive refresh lease release failed error=%s: %s", type(exc).__name__, exc)
