"""Period-specific rankings of stored TCG observations. Never fetches providers.

A worker publishes every game/period ranking (market_snapshots); public reads only
paginate it. The full ranking cannot fit the API's five-second SQL deadline on
production data (QueryCanceled on 2026-10-26).
"""
import json
import math
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import and_, func, not_, select
from sqlalchemy.orm import Session, aliased

from app.config import get_settings
from app.models import Card, CatalogPriceCandidate, PriceObservation, Set
from app.schemas.cards import MarketMoverItem
from app.services import market_snapshots
from app.services.image_delivery import card_image_url
from app.services.market_data_service import estimated_price_change
from app.services.price_sources import market_observation
from app.services.product_metadata import sealed_product

GAMES = ("pokemon", "pokemon-japan")
PERIODS = ("24h", "7d", "30d")
SNAPSHOT_NAME = "movers"
PARTS = [f"{game}:{period}" for game in GAMES for period in PERIODS]
# Rows kept per direction; totals still count every mover. Bounds the snapshot
# in the 32 MB evicting cache Redis.
SNAPSHOT_LIMIT = 1000


class MoversRanking(BaseModel):
    gainers: list[MarketMoverItem]
    losers: list[MarketMoverItem]
    total_gainers: int
    total_losers: int


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


def build_parts(db: Session, now: datetime) -> dict[str, str]:
    return {part: json.dumps({"updated_at": now.isoformat(), **ranking.model_dump(mode="json")})
            for part, ranking in build_rankings(db, now).items()}


def refresh_snapshot(*, force=False) -> bool:
    return market_snapshots.refresh(SNAPSHOT_NAME, PARTS, build_parts, force=force)


def stored_movers(db: Session, game: str, period: str) -> tuple[MoversRanking, datetime]:
    """Serve the worker snapshot; compute on request only when Redis is unreachable."""
    data = market_snapshots.read(SNAPSHOT_NAME, f"{game}:{period}")
    if data is not None:
        return MoversRanking.model_validate(data), datetime.fromisoformat(data["updated_at"])
    now = datetime.now(UTC)
    return build_rankings(market_snapshots.on_demand_session(db), now)[f"{game}:{period}"], now
