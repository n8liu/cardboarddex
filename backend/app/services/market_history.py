"""Source-aware history composition. Reads never create cutover records or call providers."""
from datetime import UTC, date, datetime, timedelta
from sqlalchemy import select, func
from app.models import Card, Set, PriceObservation, MarketHistory, MarketHistoryTransition
from app.services.ppt_ingestion import digest

KEYS = ('language', 'currency', 'printing', 'condition', 'grade', 'metric')


def dimensions(value):
    result = {key: value.get(key) for key in KEYS}
    result['printing'] = 'Normal' if result['printing'] == 'Standard' else result['printing']
    result['condition'] = 'Near Mint' if result['condition'] == 'NM' else result['condition']
    return result


def legacy_series(db, card_id, days=730, stored=None):
    cutoff = datetime.now(UTC).date() - timedelta(days=days)
    if stored is None:
        language = db.scalar(select(Set.series).join(Card, Card.set_id == Set.id).where(Card.id == card_id))
        language = 'japanese' if language == 'Pokemon Japan' else 'english'
    else:
        language = stored['language']
    grouped = {}
    def add(dim, at, price, fetched):
        if not at or not cutoff <= at <= datetime.now(UTC).date() or price is None or price <= 0:
            return
        dim = dimensions(dim)
        key = digest([card_id, dim])
        entry = grouped.setdefault(key, dict(dim, id=key, provider='tcgapi', fetched_at=fetched, points={}))
        entry['fetched_at'] = fetched
        entry['points'][at.isoformat()] = dict(date=at.isoformat(), price=float(price), sales_count=None, source='tcgapi')
    # Ordered observations use the latest actual quote per dimension/day, never an average of printings.
    for row in (stored["observations"] if stored is not None else db.scalars(select(PriceObservation).where(PriceObservation.card_id == card_id,
        PriceObservation.provider == 'tcgapi', PriceObservation.grading_company.is_(None),
        func.coalesce(PriceObservation.provider_updated_at, PriceObservation.observed_at) >= datetime.combine(cutoff, datetime.min.time(), UTC)).order_by(
            PriceObservation.provider_updated_at.asc().nullsfirst(), PriceObservation.observed_at, PriceObservation.id))):
        at = (row.provider_updated_at or row.observed_at)
        add(dict(language=language, currency=row.currency, printing=row.printing, condition=row.condition,
                 grade=None, metric='market'), at.date() if at else None, row.price, row.observed_at)
    # Explicit daily history wins over undimensioned snapshots for its own printing only.
    for row in (stored["legacy_history"] if stored is not None else db.scalars(select(MarketHistory).where(MarketHistory.card_id == card_id, MarketHistory.day >= cutoff).order_by(MarketHistory.day))):
        add(dict(language=language, currency='USD', printing=row.printing, condition=None, grade=None, metric='market'),
            row.day, row.market_price, row.fetched_at)
    return [dict(item, points=list(item['points'].values())) for item in grouped.values()]


def establish_transitions(db, product, now=None):
    """Called by bounded cutover tooling and post-cutover ingestion, under the card lock."""
    now = now or datetime.now(UTC)
    legacy = legacy_series(db, product.card_id, days=36500)
    for quote in product.quotes:
        if quote.get('grade') or quote.get('metric') != 'market':
            continue
        dim = dimensions(quote)
        key = digest([product.card_id, dim])
        if db.get(MarketHistoryTransition, key):
            continue
        # Unknown condition is retained separately but cannot overlap the continuation in time.
        dates = [p['date'] for s in legacy if s['printing'] == dim['printing'] and s['currency'] == dim['currency']
                 and s['condition'] in (None, 'Unknown', dim['condition']) for p in s['points']]
        boundary = date.fromisoformat(quote['price_date'])
        if dates:
            boundary = max(boundary, date.fromisoformat(max(dates)) + timedelta(days=1))
        db.add(MarketHistoryTransition(id=key, card_id=product.card_id, product_id=product.id,
            dimensions=dim, cutover_date=boundary, created_at=now))


def unified_history(db, card_id, provider_history, days=365, stored=None):
    legacy = {s['id']: s for s in legacy_series(db, card_id, days, stored)}
    transitions = {t.id: t for t in (stored["transitions"] if stored is not None else db.scalars(select(MarketHistoryTransition).where(MarketHistoryTransition.card_id == card_id)))}
    output = []
    for series in provider_history:
        dim = dimensions(series)
        key = digest([card_id, dim])
        transition = transitions.get(key)
        old = legacy.pop(key, None) if dim['condition'] not in (None, 'Unknown') else None
        if series.get('grade'):
            # Graded sold averages never continue asking-price series or seven-day medians.
            output.append(dict(series, points=[dict(p, source='pokemonpricetracker') for p in series['points']]))
            continue
        if transition is None:
            if old:
                legacy[key] = old
            continue  # Cutover must be explicitly seeded, not invented by a public GET.
        boundary = transition.cutover_date.isoformat()
        points = [p for p in (old or {}).get('points', []) if p['date'] < boundary]
        points += [dict(p, source='pokemonpricetracker') for p in series['points'] if p['date'] >= boundary]
        output.append(dict(series, **dim, id=key, provider='market', cutover_date=boundary,
                           points=sorted(points, key=lambda p: p['date'])))
    output.extend(legacy.values())
    return output


def load_history_inputs(db, card_ids, days):
    """Batch portfolio inputs: fixed query count, bounded request IDs and date window."""
    from app.models import PPTProduct, PPTHistory
    cutoff = datetime.now(UTC).date() - timedelta(days=min(days, 730))
    result = {cid: {'language': 'english', 'observations': [], 'legacy_history': [],
                    'products': [], 'history': [], 'transitions': []} for cid in card_ids}
    for cid, series in db.execute(select(Card.id, Set.series).join(Set, Card.set_id == Set.id).where(Card.id.in_(card_ids))):
        result[cid]['language'] = 'japanese' if series == 'Pokemon Japan' else 'english'
    queries = [
        ('observations', select(PriceObservation).where(PriceObservation.card_id.in_(card_ids), PriceObservation.provider == 'tcgapi',
             PriceObservation.grading_company.is_(None), func.coalesce(PriceObservation.provider_updated_at, PriceObservation.observed_at) >= datetime.combine(cutoff, datetime.min.time(), UTC))
             .order_by(PriceObservation.provider_updated_at.asc().nullsfirst(), PriceObservation.observed_at, PriceObservation.id)),
        ('legacy_history', select(MarketHistory).where(MarketHistory.card_id.in_(card_ids), MarketHistory.day >= cutoff).order_by(MarketHistory.day)),
        ('products', select(PPTProduct).where(PPTProduct.card_id.in_(card_ids), PPTProduct.status == 'matched')),
        ('history', select(PPTHistory).where(PPTHistory.card_id.in_(card_ids), PPTHistory.month >= cutoff.isoformat()[:7])),
        ('transitions', select(MarketHistoryTransition).where(MarketHistoryTransition.card_id.in_(card_ids))),
    ]
    for key, query in queries:
        for row in db.scalars(query.execution_options(yield_per=250)):
            result[row.card_id][key].append(row)
    return result
