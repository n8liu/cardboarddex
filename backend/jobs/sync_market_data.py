"""Bounded individual history ingestion and catalog discovery (no bulk endpoints)."""
import argparse
import logging
from datetime import UTC, datetime, timedelta
import httpx
from celery import shared_task
from sqlalchemy import delete, select
from app.database import SessionLocal
from app.models import Card, MarketHistory, ProviderCardState, CatalogSnapshot
from app.providers.limiter import ProviderRequestLimitExceeded
from app.services.market_data_service import normalize_history
from app.tcgapi.client import TCGAPIClient

logger = logging.getLogger(__name__)


def sync_history(db, client, card):
    now = datetime.now(UTC)
    source = db.scalar(select(ProviderCardState).where(ProviderCardState.card_id == card.id, ProviderCardState.provider == "tcgapi"))
    source_id = source.provider_card_id if source and source.provider_card_id else card.id
    payload = client.get_history(source_id)
    points = normalize_history(payload, now.date())
    # Idempotent replacement of reported rows also accepts provider corrections.
    for point in points:
        db.merge(MarketHistory(card_id=card.id, fetched_at=now, **point))
    db.execute(delete(MarketHistory).where(MarketHistory.card_id == card.id, MarketHistory.day < now.date() - timedelta(days=372)))
    state = db.scalar(select(ProviderCardState).where(ProviderCardState.card_id == card.id, ProviderCardState.provider == "tcgapi_history"))
    if state is None:
        state = ProviderCardState(card_id=card.id, provider="tcgapi_history", match_status="ready")
        db.add(state)
    state.match_status = "ready" if points else "unavailable"
    state.last_synced_at = now
    state.payload = {"success_at": now.isoformat(), "rows_received": len(points)}
    db.commit()
    return len(points)


def sync_catalog_snapshot(db, client, game):
    payload = client.get_game(game).get("data")
    if not isinstance(payload, dict):
        logger.error("Malformed provider game response game=%s", game)
        raise ValueError("Malformed game response")
    # Consume every page before replacing the last successful snapshot.
    sets = list(client.iter_game_sets(game))
    if len({str(row["id"]) for row in sets}) != len(sets):
        logger.error("Duplicate provider set IDs game=%s", game)
        raise ValueError("Duplicate catalog sets")
    db.merge(CatalogSnapshot(game=game, payload={"game": payload, "sets": sets}, fetched_at=datetime.now(UTC)))
    db.commit()
    return len(sets)


def record_failure(db, card_id, status):
    state = db.scalar(select(ProviderCardState).where(ProviderCardState.card_id == card_id, ProviderCardState.provider == "tcgapi_history"))
    if state is None:
        state = ProviderCardState(card_id=card_id, provider="tcgapi_history", match_status=status)
        db.add(state)
    state.match_status = status
    state.last_synced_at = datetime.now(UTC)
    db.commit()


@shared_task(name="jobs.sync_market_data.sync_market_data")
def sync_market_data(limit=5, card_ids=None, discover=False):
    if not 1 <= limit <= 50 or (card_ids and len(card_ids) > limit):
        raise ValueError("limit must be 1–50 and bound the requested card IDs")
    client = TCGAPIClient()
    result = {"products": 0, "history_rows": 0, "discovered_sets": 0, "failures": 0}
    with SessionLocal() as db:
        if discover:
            for game in ("pokemon", "pokemon-japan"):
                try:
                    result["discovered_sets"] += sync_catalog_snapshot(db, client, game)
                except Exception as exc:
                    db.rollback()
                    logger.exception("Catalog snapshot failed game=%s error=%s: %s", game, type(exc).__name__, exc)
                    raise
        state = ProviderCardState
        query = select(Card).outerjoin(state, (state.card_id == Card.id) & (state.provider == "tcgapi_history"))
        if card_ids:
            query = query.where(Card.id.in_(card_ids))
        else:
            query = query.where((state.id.is_(None)) | (state.last_synced_at < datetime.now(UTC) - timedelta(hours=24)))
        cards = list(db.scalars(query.order_by(state.last_synced_at.asc().nullsfirst(), Card.id).limit(limit)))
        for card in cards:
            card_id = card.id
            try:
                result["history_rows"] += sync_history(db, client, card)
                result["products"] += 1
            except ProviderRequestLimitExceeded as exc:
                db.rollback()
                logger.warning("History quota exhausted card_id=%s error=%s: %s", card_id, type(exc).__name__, exc)
                raise
            except httpx.HTTPStatusError as exc:
                db.rollback()
                code = exc.response.status_code
                logger.error("History sync HTTP failure card_id=%s status=%s error=%s: %s", card_id, code, type(exc).__name__, exc)
                record_failure(db, card_id, "restricted" if code in (401, 402, 403) else "unavailable" if code == 404 else "error")
                result["failures"] += 1
                if code in (401, 402, 403, 429) or code >= 500:
                    raise
            except Exception as exc:
                db.rollback()
                logger.exception("History sync failed card_id=%s error=%s: %s", card_id, type(exc).__name__, exc)
                record_failure(db, card_id, "error")
                result["failures"] += 1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--card-id", action="append", dest="card_ids")
    parser.add_argument("--discover", action="store_true", help="Refresh both Pokémon catalog snapshots before history")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    result = sync_market_data(**vars(args))
    logger.info("Market data sync result=%s", result)
    if result["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
