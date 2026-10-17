"""Small, resumable PPT batches; no sleeping on the shared Celery worker."""
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from celery import shared_task
from sqlalchemy import func, or_, select
from app.common.redis import get_durable_redis
from app.config import get_settings
from app.database import SessionLocal
from app.models import Card, Set, PPTCheckpoint, PPTProduct
from app.providers.ppt import PPTBlocked, PPTClient, PREFIX, RELEASE
from app.services.ppt_ingestion import ingest, map_product, index_legacy_identities
from app.services.passive_refresh import interest_scores, rank_priority, percentiles

logger = logging.getLogger(__name__)
SEGMENTS = ("english:cards", "japanese:cards", "english:sealed", "japanese:sealed")


def checkpoint(db, key, default):
    row = db.get(PPTCheckpoint, key)
    if row is None:
        row = PPTCheckpoint(key=key, payload=default)
        db.add(row)
        db.flush()
    return row


def discovery_step(db, client, segment, now):
    """One bounded request, checkpointed in the same transaction as discoveries."""
    if not index_legacy_identities(db):
        return
    language, kind = segment.split(":")
    sets_state = checkpoint(db, "sets:" + segment, {"offset": 0, "sets": [], "complete": False})
    state = dict(sets_state.payload)
    if not state["complete"]:
        db.commit()
        rows = client.request("sets", lane="discovery", language=language, limit=100, offset=state["offset"])
        state["sets"] = state["sets"] + rows
        state["offset"] += len(rows)
        state["complete"] = len(rows) < 100
        sets_state.payload = state
        return
    cursor = checkpoint(db, "discover:" + segment, {"set": 0, "offset": 0})
    pos = dict(cursor.payload)
    if pos["set"] >= len(state["sets"]):
        # Once a full scan completes, refresh the set index on the next UTC day.
        if pos.get("completed") == now.date().isoformat():
            raise PPTBlocked("discovery_complete")
        cursor.payload = {"set": 0, "offset": 0, "completed": now.date().isoformat()}
        sets_state.payload = {"offset": 0, "sets": [], "complete": False}
        return
    metadata = state["sets"][pos["set"]]
    set_id = metadata.get("tcgPlayerNumericId") or metadata.get("id")
    db.commit()
    rows = client.request("cards" if kind == "cards" else "sealed-products", lane="discovery",
                          language=language, setId=set_id, limit=25, offset=pos["offset"])
    for row in rows:
        map_product(db, row, language, kind, metadata)
    pos["offset"] += len(rows)
    if len(rows) < 25:
        pos["set"] += 1
        pos["offset"] = 0
    cursor.payload = pos


def rank_ppt_priority(db, popularity, limit=1500):
    rows = list(db.execute(select(PPTProduct.card_id, PPTProduct.primary_price, Set.release_date).join(
        Card, PPTProduct.card_id == Card.id).join(Set, Card.set_id == Set.id).where(PPTProduct.status == "matched")))
    if not rows:
        return rank_priority(db, popularity, limit)
    pop = percentiles({cid: popularity.get(cid) or None for cid, _, _ in rows})
    age = percentiles({cid: released.toordinal() if released else None for cid, _, released in rows})
    prices = percentiles({cid: amount for cid, amount, _ in rows})
    ranked = sorted(pop, key=lambda cid: (-(.5 * pop[cid] + .25 * age[cid] + .25 * prices[cid]), cid))
    # Preserve existing popular IDs while their mappings are still being discovered.
    if len(ranked) < limit:
        seen = set(ranked)
        ranked.extend(cid for cid in rank_priority(db, popularity, limit) if cid not in seen)
    return ranked[:limit]


def due_query(now):
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return select(PPTProduct).where(PPTProduct.status == "matched",
        or_(PPTProduct.last_success_at.is_(None), PPTProduct.last_success_at < start),
        or_(PPTProduct.retry_at.is_(None), PPTProduct.retry_at <= now))


def select_product(db, now, lane, priority):
    query = due_query(now)
    if lane == "priority":
        query = query.where(PPTProduct.card_id.in_(priority), PPTProduct.failures == 0)
    elif lane == "retry":
        query = query.where(PPTProduct.failures > 0)
    else:
        query = query.where(PPTProduct.failures == 0)
        if now.hour < 22:
            query = query.where(PPTProduct.card_id.not_in(priority))
        if lane == "graded":
            query = query.where(PPTProduct.segment.in_(("english:cards", "japanese:cards")))
    sub = query.subquery()
    counts = dict(db.execute(select(sub.c.segment, func.count()).group_by(sub.c.segment)).all())
    if not counts:
        return None
    progress = checkpoint(db, "rotation:" + now.date().isoformat(), {})
    served = dict(progress.payload)
    total = sum(counts.values())
    # Proportional backlog, reserving a 10% floor for each nonempty segment.
    shares = {s: .1 + (1 - .1 * len(counts)) * n / total for s, n in counts.items()}
    segment = min(counts, key=lambda s: (served.get(s, 0) / shares[s], s))
    product = db.scalar(query.where(PPTProduct.segment == segment).order_by(
        PPTProduct.last_success_at.asc().nullsfirst(), PPTProduct.id).limit(1))
    if product:
        served[segment] = served.get(segment, 0) + 1
        progress.payload = served
    return product


@shared_task(name="jobs.sync_ppt.sync_ppt", autoretry_for=(), max_retries=0)
def sync_ppt():
    settings = get_settings()
    if not settings.ppt_ingestion_enabled:
        return {"status": "disabled"}
    redis = get_durable_redis()
    token = uuid.uuid4().hex
    lease = PREFIX + ":batch"
    if not redis.set(lease, token, nx=True, ex=240):
        return {"status": "leased"}
    client = PPTClient()
    completed = 0
    started = time.monotonic()
    try:
        with SessionLocal() as db:
            now = datetime.now(UTC)
            weekly = now.date() - timedelta(days=now.weekday())
            pool = checkpoint(db, "priority:" + weekly.isoformat(), {})
            if "cards" not in pool.payload:
                pool.payload = {"cards": rank_ppt_priority(db, interest_scores(now.timestamp()), 1500)}
                db.commit()
            priority = pool.payload["cards"]
            scheduling = checkpoint(db, "scheduler", {"turn": 0})
            turn = scheduling.payload["turn"]
            db.commit()
            # Priority gets 3/10 slots; rotation gets 5/10, discovery 1/10,
            # retries get 1/10. Extra graded credits attach to rotation requests. Exhausted/empty lanes yield.
            lanes = ("priority", "rotation", "rotation", "priority", "discovery",
                     "rotation", "priority", "rotation", "rotation", "retry")
            for _ in range(settings.ppt_batch_size):
                if time.monotonic() - started > 25:
                    break
                now = datetime.now(UTC)
                lane = lanes[turn % len(lanes)]
                product_id = None
                try:
                    if lane == "discovery":
                        discovery_step(db, client, SEGMENTS[(turn // len(lanes)) % 4], now)
                    else:
                        product = select_product(db, now, lane, priority)
                        if product is None and now.hour >= 22:
                            lane = "rotation"
                            product = select_product(db, now, lane, priority)
                        if product is None:
                            continue
                        product_id = product.id
                        language, kind = product.segment.split(":")
                        bonus_graded = (lane == "rotation" and kind == "cards" and int(redis.get(
                            f"{PREFIX}:lane:{int(now.timestamp() // 86400)}:graded") or 0) < 500)
                        db.commit()  # Release the connection during provider I/O.
                        rows = client.request("cards" if kind == "cards" else "sealed-products", lane=lane,
                            language=language, tcgPlayerId=product.provider_id, limit=1, includeHistory=True, bonus_graded=bonus_graded,
                            includeEbay=kind == "cards" and (bonus_graded or lane in {"priority", "retry"}))
                        if len(rows) != 1:
                            raise ValueError("PPT product lookup returned no product")
                        ingest(db, product, rows[0], now)
                    db.commit()
                    completed += 1
                except PPTBlocked as exc:
                    db.rollback()
                    if str(exc) in {"minute", "cooldown", "in_flight", "daily", "missing_api_key"}:
                        break
                except Exception as exc:
                    db.rollback()
                    logger.error("PPT batch failed product=%s lane=%s error=%s: %s", product_id, lane, type(exc).__name__, exc)
                    if product_id:
                        product = db.get(PPTProduct, product_id)
                        product.failures += 1
                        product.retry_at = now + timedelta(minutes=min(1440, 15 * 2 ** min(product.failures, 7)))
                        db.commit()
                    break
                finally:
                    turn += 1
            scheduling = db.get(PPTCheckpoint, "scheduler")
            scheduling.payload = {"turn": turn}
            db.commit()
        return {"status": "complete", "requests_completed": completed}
    finally:
        client.close()
        redis.eval(RELEASE, 1, lease, token)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(sync_ppt())
