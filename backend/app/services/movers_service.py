from app.services.price_sources import market_observation
"""Period-specific rankings of stored TCG observations. Never fetches providers."""
import math
from datetime import UTC, datetime

from fastapi import Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.common.response_cache import cached_read
from app.models import Card, PriceObservation, Set
from app.schemas.cards import MarketMoverItem
from app.services.image_delivery import card_image_url
from app.services.market_data_service import estimated_price_change


@cached_read('stored-movers-v2', fresh=900, maximum=1800)
def stored_movers(response: Response, db: Session, game: str, period: str) -> dict[str, list[MarketMoverItem]]:
    latest = select(PriceObservation.id, func.row_number().over(
        partition_by=PriceObservation.card_id,
        order_by=(PriceObservation.provider_updated_at.desc().nullslast(),
                  PriceObservation.observed_at.desc(), PriceObservation.id.desc()),
    ).label('position')).where(
        market_observation(), PriceObservation.currency == 'USD',
        PriceObservation.grading_company.is_(None), PriceObservation.observed_at <= datetime.now(UTC),
    ).subquery()
    # Only select needed scalars, not the historical provider payloads.
    query = select(Card.id, Card.name, Card.number, Set.name.label('set_name'), Card.set_id,
        PriceObservation.price, PriceObservation.observed_at, PriceObservation.provider, PriceObservation.printing,
        PriceObservation.payload[f'price_change_{period}'].as_string().label('change'),
    ).join(Set, Set.id == Card.set_id).join(PriceObservation, PriceObservation.card_id == Card.id).join(
        latest, and_(latest.c.id == PriceObservation.id, latest.c.position == 1),
    ).where(Card.name.not_ilike('%code card%'))
    if game == 'pokemon-japan':
        query = query.where(Set.series == 'Pokemon Japan')
    else:
        query = query.where(or_(Set.series.is_(None), Set.series != 'Pokemon Japan'))
    result = {'gainers': [], 'losers': []}
    for row in db.execute(query.execution_options(yield_per=500)):
        try:
            price, change = float(row.price), float(row.change)
        except (ValueError, TypeError):
            continue
        if not math.isfinite(price) or not math.isfinite(change) or price <= 0 or change == 0 or change <= -100:
            continue
        direction = 'up' if change > 0 else 'down'
        comparison = estimated_price_change(price, change)
        if row.provider == "pokemonpricetracker":
            comparison["comparison_source"] = "pokemonpricetracker_history"
        result['gainers' if direction == 'up' else 'losers'].append(MarketMoverItem(
            card_id=row.id, market_source=row.provider, name=row.name, set_name=row.set_name, set_id=row.set_id,
            number=row.number, printing=row.printing, image_url=card_image_url(row.id), market_price=price,
            price_change_percentage=change, **comparison,
            period=period, direction=direction, last_updated_at=row.observed_at,
        ))
    result['gainers'].sort(key=lambda item: (-item.price_change_percentage, item.card_id))
    result['losers'].sort(key=lambda item: (item.price_change_percentage, item.card_id))
    return result
