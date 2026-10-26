"""Period-specific rankings of stored TCG observations. Never fetches providers.

A worker publishes every game/period ranking in one snapshot; public reads only
paginate it. The full ranking cannot fit the API's five-second SQL deadline on
production data (QueryCanceled on 2026-10-26).
"""
import logging
import math
import time
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, func, not_, select, text
from sqlalchemy.orm import Session, aliased

from app.common.redis import get_redis
from app.common.response_cache import _PUBLISH, _RELEASE
from app.config import get_settings
from app.database import SessionLocal
from app.models import Card, CatalogPriceCandidate, PriceObservation, Set
from app.schemas.cards import MarketMoverItem
from app.services.image_delivery import card_image_url
from app.services.market_data_service import estimated_price_change
from app.services.price_sources import market_observation
from app.services.product_metadata import sealed_product

logger = logging.getLogger(__name__)

GAMES = ("pokemon", "pokemon-japan")
PERIODS = ("24h", "7d", "30d")
# Rows kept per direction; totals still count every mover. Bounds the snapshot
# in the 32 MB evicting cache Redis.
SNAPSHOT_LIMIT = 1000
# Refreshed every 5 minutes. An older snapshot is still served (and logged) for a
# day, so a stopped worker degrades to old prices instead of 503s.
SNAPSHOT_FRESH_SECONDS = 1800
SNAPSHOT_MAX_SECONDS = 86400
SNAPSHOT_LEASE_SECONDS = 120
# Worker-only bound; public SQL keeps its five-second deadline.
SNAPSHOT_STATEMENT_TIMEOUT = "30000ms"
# Last parsed snapshot per API process, so a page read does not re-validate ~12k items.
_parsed: tuple[str, "MoversSnapshot"] | None = None


class MoversRanking(BaseModel):
    gainers: list[MarketMoverItem]
    losers: list[MarketMoverItem]
    total_gainers: int
    total_losers: int


class MoversSnapshot(BaseModel):
    updated_at: datetime
    rankings: dict[str, MoversRanking]


def snapshot_key() -> str:
    source_key = "ppt" if get_settings().ppt_primary_enabled else "legacy"
    return f"cardboarddex:{source_key}:movers-snapshot:v1"


def _current_rows(db: Session, now: datetime):
    """One row per card: its current raw USD market observation with every period's change."""
    changes = [PriceObservation.payload[f"price_change_{period}"].as_string().label(period) for period in PERIODS]
    columns = (Card.id, Card.name, Card.number, Card.set_id, Set.name.label("set_name"), Set.series,
               PriceObservation.price, PriceObservation.observed_at, PriceObservation.provider,
               PriceObservation.printing, *changes)
    settings = get_settings()
    if settings.catalog_current_prices_enabled:
        # The catalog projection already marks each card's current observation with the
        # same preference as market_observation, so nothing ranks price_observations.
        candidate = aliased(CatalogPriceCandidate)
        chosen = candidate.selected if settings.ppt_primary_enabled else candidate.provider == "tcgapi"
        query = select(*columns).join(candidate, and_(candidate.card_id == Card.id, chosen)).join(
            PriceObservation, PriceObservation.id == candidate.observation_id).where(
            PriceObservation.currency == "USD", PriceObservation.grading_company.is_(None),
            PriceObservation.observed_at <= now)
    else:
        latest = select(PriceObservation.id, func.row_number().over(
            partition_by=PriceObservation.card_id,
            order_by=(PriceObservation.provider_updated_at.desc().nullslast(),
                      PriceObservation.observed_at.desc(), PriceObservation.id.desc()),
        ).label("position")).where(
            market_observation(), PriceObservation.currency == "USD",
            PriceObservation.grading_company.is_(None), PriceObservation.observed_at <= now,
        ).subquery()
        query = select(*columns).join(PriceObservation, PriceObservation.card_id == Card.id).join(
            latest, and_(latest.c.id == PriceObservation.id, latest.c.position == 1))
    # Movers lists singles only; sealed products belong to the sealed page.
    query = query.join(Set, Set.id == Card.set_id).where(
        Card.name.not_ilike("%code card%"), not_(sealed_product()))
    return db.execute(query.execution_options(yield_per=500))


def _item(row, period: str, price: float, change: float) -> MarketMoverItem:
    comparison = estimated_price_change(price, change)
    if row.provider == "pokemonpricetracker":
        comparison["comparison_source"] = "pokemonpricetracker_history"
    return MarketMoverItem(
        card_id=row.id, market_source=row.provider, name=row.name, set_name=row.set_name, set_id=row.set_id,
        number=row.number, printing=row.printing, image_url=card_image_url(row.id), market_price=price,
        price_change_percentage=change, **comparison,
        period=period, direction="up" if change > 0 else "down", last_updated_at=row.observed_at,
    )


def build_rankings(db: Session, now: datetime, limit: int = SNAPSHOT_LIMIT) -> dict[str, MoversRanking]:
    """Every game/period ranking from a single read of current prices."""
    movers = {(game, period): ([], []) for game in GAMES for period in PERIODS}
    for row in _current_rows(db, now):
        game = "pokemon-japan" if row.series == "Pokemon Japan" else "pokemon"
        for period in PERIODS:
            try:
                price, change = float(row.price), float(getattr(row, period))
            except (ValueError, TypeError):
                continue
            if not math.isfinite(price) or not math.isfinite(change) or price <= 0 or change == 0 or change <= -100:
                continue
            gainers, losers = movers[(game, period)]
            (gainers if change > 0 else losers).append((change, row.id, price, row))
    rankings = {}
    for (game, period), (gainers, losers) in movers.items():
        gainers.sort(key=lambda entry: (-entry[0], entry[1]))
        losers.sort(key=lambda entry: (entry[0], entry[1]))
        rankings[f"{game}:{period}"] = MoversRanking(
            gainers=[_item(row, period, price, change) for change, _, price, row in gainers[:limit]],
            losers=[_item(row, period, price, change) for change, _, price, row in losers[:limit]],
            total_gainers=len(gainers), total_losers=len(losers),
        )
    return rankings


def refresh_snapshot() -> bool:
    started = time.monotonic()
    redis = get_redis()
    if redis is None:
        logger.warning("Movers refresh unavailable: Redis client unavailable")
        return False
    key, token = snapshot_key(), uuid.uuid4().hex
    acquired = False
    try:
        acquired = bool(redis.set(key + ":lock", token, nx=True, ex=SNAPSHOT_LEASE_SECONDS))
        if not acquired:
            return False
        now = datetime.now(UTC)
        with SessionLocal() as db:
            if db.get_bind().dialect.name == "postgresql":
                db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
                db.execute(text(f"SET LOCAL statement_timeout = '{SNAPSHOT_STATEMENT_TIMEOUT}'"))
            raw = MoversSnapshot(updated_at=now, rankings=build_rankings(db, now)).model_dump_json()
        published = bool(redis.eval(_PUBLISH, 2, key + ":lock", key, token, raw, SNAPSHOT_MAX_SECONDS))
        logger.info("Movers refresh published=%s duration_ms=%.1f bytes=%d", published,
                    (time.monotonic() - started) * 1000, len(raw.encode()))
        return published
    except Exception as exc:
        logger.exception("Movers refresh failed error=%s: %s", type(exc).__name__, exc)
        return False
    finally:
        if acquired:
            try:
                redis.eval(_RELEASE, 1, key + ":lock", token)
            except Exception as exc:
                logger.warning("Movers lock release failed error=%s: %s", type(exc).__name__, exc)


def read_snapshot(redis) -> MoversSnapshot | None:
    """Return the published snapshot; None only when Redis itself is unreachable."""
    global _parsed
    try:
        raw = redis.get(snapshot_key())
    except Exception as exc:
        logger.warning("Movers snapshot read failed error=%s: %s", type(exc).__name__, exc)
        return None
    if raw:
        try:
            snapshot = _parsed[1] if _parsed is not None and _parsed[0] == raw else MoversSnapshot.model_validate_json(raw)
            _parsed = (raw, snapshot)
            age = (datetime.now(UTC) - snapshot.updated_at).total_seconds()
            if 0 <= age < SNAPSHOT_MAX_SECONDS:
                if age >= SNAPSHOT_FRESH_SECONDS:
                    logger.warning("Movers snapshot stale age_seconds=%.0f; is the worker running?", age)
                return snapshot
        except ValueError as exc:
            logger.warning("Movers snapshot invalid error=%s: %s", type(exc).__name__, exc)
    raise HTTPException(503, "Market movers temporarily unavailable",
                        headers={"Retry-After": "60", "Cache-Control": "no-store"})


def stored_movers(db: Session, game: str, period: str) -> tuple[MoversRanking, datetime]:
    """Serve the worker snapshot; compute on request only when Redis is unreachable."""
    redis = get_redis()
    snapshot = read_snapshot(redis) if redis is not None else None
    if snapshot is not None:
        return snapshot.rankings[f"{game}:{period}"], snapshot.updated_at
    logger.warning("Movers serving on-demand fallback: Redis unavailable")
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL statement_timeout = '5000ms'"))
    now = datetime.now(UTC)
    return build_rankings(db, now)[f"{game}:{period}"], now
