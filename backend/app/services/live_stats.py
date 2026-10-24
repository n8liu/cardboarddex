"""Worker-published Live Comps totals. Public reads never rebuild a snapshot."""
import json
import logging
import time
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import and_, case, func, select, text, union_all

from app.common.redis import get_redis
from app.common.response_cache import _PUBLISH, _RELEASE
from app.config import get_settings
from app.database import SessionLocal
from app.models import Card, ListingAssessment as A, PriceObservation as O, Set
from app.providers.ppt import PROVIDER
from app.schemas.cards import LiveStatsResponse
from app.services import listing_quality
from app.services.price_sources import public_observation

logger = logging.getLogger(__name__)
FRESH_SECONDS = 60
MAX_SECONDS = 1800
# Kept past MAX_SECONDS so a stopped worker shows dated totals, not a 503.
RETAIN_SECONDS = 86400
LEASE_SECONDS = 30
LEGACY_KEY = "cardboarddex:live_stats:legacy:v1"
LEGACY_SECONDS = 86400


def snapshot_key():
    return (f"cardboarddex:live_stats:v2:{listing_quality.MATCHER_VERSION}:"
            f"ppt-{int(get_settings().ppt_primary_enabled)}")


def _plain(condition):
    return select(O.provider, O.grading_company).join(Card, O.card_id == Card.id).join(
        Set, Card.set_id == Set.id).where(condition, public_observation())


def _tally(db, *queries):
    rows = (union_all(*queries) if len(queries) > 1 else queries[0]).subquery()
    return list(db.execute(select(func.count(),
        func.count(case((rows.c.provider == "ebay", 1))),
        func.count(case((rows.c.provider == "tcgapi", 1))),
        func.count(case((rows.c.provider == PROVIDER, 1))),
        func.count(rows.c.grading_company)).select_from(rows)).one())


def legacy_counts(db):
    """Retired providers (tcgapi) no longer ingest, so their totals are counted once a day."""
    return _tally(db, _plain(and_(O.provider.not_ilike("%ebay%"), O.provider != PROVIDER)))


def calculate_snapshot(db, legacy=None):
    # Disjoint branches avoid correlated evidence probes over all history. Only the
    # growing providers are recounted; an exact provider match keeps the index range small.
    matched = select(O.provider, O.grading_company).select_from(A).join(O, and_(
        O.card_id == A.card_id, O.provider_card_id == A.item_id,
        O.payload["assessment_fingerprint"].as_string() == A.fingerprint,
    )).join(Card, O.card_id == Card.id).join(Set, Card.set_id == Set.id).where(
        O.provider.ilike("%ebay%"), public_observation(),
        A.version == listing_quality.MATCHER_VERSION, A.status == "matched")
    current = _tally(db, _plain(O.provider == PROVIDER), matched)
    result = [a + b for a, b in zip(legacy if legacy is not None else legacy_counts(db), current)]
    return LiveStatsResponse(total_items=result[0], total_ebay_updates=result[1],
        total_tcg_updates=result[2], total_legacy_updates=result[2], total_ppt_updates=result[3], graded_updates_count=result[4],
        generated_at=datetime.now(UTC), is_stale=False)


def refresh_snapshot():
    started = time.monotonic()
    redis = get_redis()
    if redis is None:
        logger.warning("Live stats refresh unavailable: Redis client unavailable")
        return False
    key, token = snapshot_key(), uuid.uuid4().hex
    acquired = False
    try:
        acquired = bool(redis.set(key + ":lock", token, nx=True, ex=LEASE_SECONDS))
        if not acquired:
            return False
        raw = redis.get(LEGACY_KEY)
        legacy = json.loads(raw) if raw else None
        if legacy is None:
            with SessionLocal() as db:
                if db.get_bind().dialect.name == "postgresql":
                    # Once a day in the worker; stays within the task's 20s limit.
                    db.execute(text("SET LOCAL statement_timeout = '15000ms'"))
                legacy = legacy_counts(db)
            redis.set(LEGACY_KEY, json.dumps(legacy), ex=LEGACY_SECONDS)
            logger.info("Live stats legacy counts refreshed totals=%s", legacy)
        with SessionLocal() as db:
            if db.get_bind().dialect.name == "postgresql":
                db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
                db.execute(text("SET LOCAL statement_timeout = '5000ms'"))
            snapshot = calculate_snapshot(db, legacy)
        published = bool(redis.eval(_PUBLISH, 2, key + ":lock", key, token,
                                    snapshot.model_dump_json(), RETAIN_SECONDS))
        logger.info("Live stats refresh published=%s duration_ms=%.1f", published,
                    (time.monotonic() - started) * 1000)
        return published
    except Exception as exc:
        logger.exception("Live stats refresh failed error=%s: %s", type(exc).__name__, exc)
        return False
    finally:
        if acquired:
            try:
                redis.eval(_RELEASE, 1, key + ":lock", token)
            except Exception as exc:
                logger.warning("Live stats lock release failed error=%s: %s", type(exc).__name__, exc)


def read_snapshot():
    snapshot = None
    try:
        redis = get_redis()
        raw = redis.get(snapshot_key()) if redis is not None else None
        if raw:
            snapshot = LiveStatsResponse.model_validate_json(raw)
            age = (datetime.now(UTC) - snapshot.generated_at).total_seconds()
            if 0 <= age < RETAIN_SECONDS:
                if age >= MAX_SECONDS:
                    logger.warning("Live stats serving stale snapshot age_seconds=%.0f", age)
                return snapshot.model_copy(update={"is_stale": age >= FRESH_SECONDS})
    except Exception as exc:
        logger.warning("Live stats snapshot read failed error=%s: %s", type(exc).__name__, exc)
    raise HTTPException(503, "Live totals temporarily unavailable",
                        headers={"Retry-After": "60", "Cache-Control": "no-store"})
