from app.services.price_sources import market_observation
"""A small, cached homepage snapshot. Never calls an upstream provider."""
import math
from datetime import UTC, datetime, timedelta
from threading import Lock

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.common.cache import TTLCache
from app.models import Card, MarketHistory, PriceObservation, ProviderCardState, Set
from app.schemas.home import HomeHighlight, HomeOverview, HomeRelease
from app.services.image_delivery import card_image_url, image_generation
from app.services.market_data_service import freshness

_cache = TTLCache(max_entries=2, ttl=300)
_lock = Lock()


def _finite(value):
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) else None


def build_home_overview(db: Session) -> HomeOverview:
    now = datetime.now(UTC)
    today = now.date()
    # Rank only IDs first; avoid loading historical JSON blobs into Python.
    latest = select(PriceObservation.id, func.row_number().over(
        partition_by=PriceObservation.card_id,
        order_by=(PriceObservation.observed_at.desc(), PriceObservation.id.desc()),
    ).label('position')).where(
        market_observation(), PriceObservation.currency == 'USD',
        PriceObservation.observed_at <= now, PriceObservation.grading_company.is_(None),
    ).subquery()
    product_type = func.coalesce(
        ProviderCardState.payload['card']['product_type'].as_string(),
        ProviderCardState.payload['card']['data']['product_type'].as_string(),
    )
    query = select(
        Card.id, Card.name, Card.rarity, Set.name.label('set_name'),
        Set.release_date, product_type.label('product_type'),
        PriceObservation.price, PriceObservation.printing, PriceObservation.observed_at,
        PriceObservation.payload['price_change_30d'].as_string().label('change'),
        PriceObservation.payload['market_price_as_of'].as_string().label('price_date'),
    ).join(Set, Card.set_id == Set.id).join(PriceObservation, PriceObservation.card_id == Card.id).join(
        latest, and_(latest.c.id == PriceObservation.id, latest.c.position == 1),
    ).outerjoin(ProviderCardState, and_(ProviderCardState.card_id == Card.id, ProviderCardState.provider == 'tcgapi')).where(
        Card.name.not_ilike('%code card%'),
        or_(Set.release_date.is_(None), Set.release_date <= today),
    )
    winners = {'gainer': None, 'loser': None, 'sealed': None}
    for row in db.execute(query.execution_options(yield_per=1000)).mappings():
        change = _finite(row['change'])
        price = _finite(row['price'])
        if change is None or change < -100 or price is None or price <= 0:
            continue
        sealed = row['product_type'] == 'Sealed Products' or (row['product_type'] is None and not row['rarity'])
        # Zero and declines never become a positive "top growth" highlight.
        kind = 'sealed' if sealed and change > 0 else 'gainer' if not sealed and change > 0 else 'loser' if not sealed and change < 0 else None
        if not kind:
            continue
        candidate = dict(row)
        candidate['change'] = change
        existing = winners[kind]
        score = -change if kind == 'loser' else change
        old_score = (-existing['change'] if kind == 'loser' else existing['change']) if existing else None
        if old_score is None or score > old_score or (score == old_score and row['id'] < existing['id']):
            winners[kind] = candidate

    highlights = {}
    for kind, row in winners.items():
        if row is None:
            highlights[kind] = None
            continue
        printing = 'Normal' if row['printing'] in (None, 'Standard') else row['printing']
        history = db.execute(select(MarketHistory.day, MarketHistory.market_price).where(
            MarketHistory.card_id == row['id'], MarketHistory.printing == printing,
            MarketHistory.day >= today - timedelta(days=30), MarketHistory.day <= today,
        ).order_by(MarketHistory.day)).all()
        from app.services.ppt_prices import market_history as ppt_market_history
        ppt_history = ppt_market_history(db, row["id"], 30)
        dated = freshness({'market_price_as_of': row['price_date']}, today=today)
        highlights[kind] = HomeHighlight(
            card_id=row['id'], name=row['name'], set_name=row['set_name'], image_url=card_image_url(row['id']),
            printing=row['printing'], market_price=float(row['price']), change_percent=row['change'],
            market_price_as_of=dated['market_price_as_of'], price_freshness=dated['price_freshness'],
            observed_at=row['observed_at'],
            history=ppt_history['points'] if ppt_history else [{'date': h.day.isoformat(), 'market_price': float(h.market_price) if h.market_price is not None else None,
                      'sales_volume': None, 'avg_sales_price': None} for h in history],
        )

    # Cap each language independently so newer English releases cannot hide Japanese sets.
    releases = []
    for game in ('pokemon', 'pokemon-japan'):
        language = Set.series == 'Pokemon Japan' if game == 'pokemon-japan' else or_(Set.series.is_(None), Set.series != 'Pokemon Japan')
        for upcoming in (False, True):
            dates = and_(Set.release_date > today, Set.release_date <= today + timedelta(days=180)) if upcoming else Set.release_date <= today
            sets = db.scalars(select(Set).where(language, dates).order_by(
                Set.release_date.asc() if upcoming else Set.release_date.desc(), Set.id,
            ).limit(2 if upcoming else 8)).all()
            for cset in sets:
                releases.append(HomeRelease(id=cset.id, name=cset.name, game=game,
                    release_date=cset.release_date, upcoming=upcoming, card_count=0, image_url=None))
    if releases:
        images = db.execute(select(Card.set_id, func.count(), func.min(Card.id),
            func.min(case((Card.name.ilike('%booster%'), Card.id), else_=None)),
        ).where(Card.set_id.in_([r.id for r in releases])).group_by(Card.set_id)).all()
        by_set = {r[0]: r for r in images}
        for release in releases:
            if row := by_set.get(release.id):
                release.card_count = row[1]
                release.image_url = card_image_url(row[3] or row[2])
    products, card_updated = db.execute(select(func.count(), func.max(Card.updated_at)).select_from(Card)).one()
    sets, set_updated = db.execute(select(func.count(), func.max(Set.updated_at)).select_from(Set)).one()
    observations, last_observed = db.execute(select(func.count(), func.max(PriceObservation.observed_at)).select_from(PriceObservation)).one()
    catalog_dates = [d.replace(tzinfo=UTC) if d.tzinfo is None else d for d in (card_updated, set_updated) if d]
    return HomeOverview(calculated_at=now, catalog_updated_at=max(catalog_dates) if catalog_dates else None,
        latest_observation_at=last_observed, products=products, sets=sets, price_observations=observations,
        releases=releases, **highlights)


def get_home_overview(db: Session) -> HomeOverview:
    key = image_generation()
    # One rebuild per process; readers share a bounded five-minute snapshot.
    with _lock:
        cached = _cache.get(key)
        if cached is not None:
            return cached
        result = build_home_overview(db)
        _cache[key] = result
        return result
