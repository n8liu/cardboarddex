"""Read-only rollout diagnostics; prints no credentials or full provider payloads."""
import json
import logging
from datetime import UTC, datetime
from sqlalchemy import String, cast, func, select
from redis.exceptions import RedisError
from app.common.redis import get_durable_redis
from app.config import get_settings
from app.database import SessionLocal
from app.models import PPTProduct, PPTHistory, PPTCurrentQuote, PriceObservation, Card, MarketHistoryTransition
from app.providers.ppt import LANES, PREFIX, PROVIDER, pacing_allowance
from jobs.sync_ppt import due_query

logger = logging.getLogger(__name__)


def report(db, redis=None, now=None):
    now = now or datetime.now(UTC)
    settings = get_settings()
    groups = db.execute(select(PPTProduct.segment, PPTProduct.status, func.count(),
        func.min(PPTProduct.last_success_at), func.max(PPTProduct.last_success_at))
        .group_by(PPTProduct.segment, PPTProduct.status)).all()
    chunks, json_bytes = db.execute(select(func.count(), func.sum(func.length(cast(PPTHistory.points, String))))).one()
    result = {"generated_at": now, "ingestion_enabled": settings.ppt_ingestion_enabled,
        "primary_enabled": settings.ppt_primary_enabled, "api_key_configured": bool(settings.ppt_api_key),
        "legacy_ingestion_retired": True,
        "daily_credit_limit": settings.ppt_daily_credit_limit, "minute_weight_limit": settings.ppt_minute_weight_limit,
        "unmapped_cards": db.scalar(select(func.count()).select_from(Card).where(~select(PPTProduct.id).where(PPTProduct.card_id == Card.id, PPTProduct.status == "matched").exists())),
        "history_transitions": db.scalar(select(func.count()).select_from(MarketHistoryTransition)),
        "coverage": [{"segment": s, "status": status, "products": n, "oldest_success": old, "newest_success": new} for s, status, n, old, new in groups],
        "due_products": db.scalar(select(func.count()).select_from(due_query(now).subquery())),
        "history_chunks": chunks, "history_json_characters": json_bytes or 0,
        "current_quotes": db.scalar(select(func.count()).select_from(PPTCurrentQuote)),
        "feed_updates": db.scalar(select(func.count()).select_from(PriceObservation).where(PriceObservation.provider == PROVIDER)),
        "quarantine_sample": [{"product_id": p.id, "reason": p.match_method, "name": p.metadata_payload.get("name")}
            for p in db.scalars(select(PPTProduct).where(PPTProduct.status == "quarantined").order_by(PPTProduct.id).limit(25))],
    }
    if redis is not None:
        try:
            bucket = int(now.timestamp() // 86400)
            result["quota"] = {"reserved_credits": int(redis.get(f"{PREFIX}:credits:{bucket}") or 0),
                "pacing_allowance": (pacing_allowance(now.timestamp(), settings.ppt_daily_credit_limit)
                                     if settings.ppt_daily_pacing_enabled else 0),
                "lanes": {lane: int(redis.get(f"{PREFIX}:lane:{bucket}:{lane}") or 0) for lane in LANES},
                "cooldown_seconds": max(0, redis.ttl(f"{PREFIX}:cooldown")),
                "request_in_flight": bool(redis.exists(f"{PREFIX}:flight"))}
        except RedisError as exc:
            logger.error("PPT quota report unavailable error=%s: %s", type(exc).__name__, exc)
            result["quota"] = {"status": "unavailable"}
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as session:
        print(json.dumps(report(session, get_durable_redis()), default=str, indent=2))


from celery import shared_task

@shared_task(name="jobs.ppt_report.publish_report")
def publish_report():
    redis = get_durable_redis()
    try:
        with SessionLocal() as db:
            payload = report(db, redis)
        redis.setex("cardboarddex:ppt:health:v1", 300, json.dumps(payload, default=str))
        return {"status": "published"}
    except Exception as exc:
        logger.exception("PPT health publication failed error=%s: %s", type(exc).__name__, exc)
        raise
