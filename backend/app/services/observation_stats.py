"""Narrow, per-card history aggregates for analytics (not completed-sale claims)."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, func, case, and_, union_all, true
from app.models import PriceObservation as O, ListingAssessment as A
from app.services.listing_quality import MATCHER_VERSION


def card_observation_stats(current_start=None, current_end=None, prior_start=None, prior_end=None):
    # Disjoint branches preserve fail-closed eBay evidence checks without a
    # correlated subquery on every historical observation. PPT aggregates are
    # excluded from legacy observation-volume metrics in both visibility modes.
    columns = (O.card_id, O.price, O.observed_at)
    plain = select(*columns).where(O.provider.not_ilike("%ebay%"), O.provider != "pokemonpricetracker")
    matched = select(*columns).select_from(A).join(O, and_(
        O.card_id == A.card_id, O.provider_card_id == A.item_id,
        O.payload["assessment_fingerprint"].as_string() == A.fingerprint,
    )).where(O.provider.ilike("%ebay%"), A.status == "matched", A.version == MATCHER_VERSION)
    rows = union_all(plain, matched).subquery()

    def window(start, end):
        conditions = []
        if start is not None:
            conditions.append(rows.c.observed_at >= start)
        if end is not None:
            conditions.append(rows.c.observed_at < end)
        return and_(*conditions) if conditions else true()

    current, prior = window(current_start, current_end), window(prior_start, prior_end)
    return select(rows.c.card_id,
        func.count().label("obs_cnt"), func.count(rows.c.price).label("price_count"),
        func.sum(rows.c.price).label("total_price"), func.avg(rows.c.price).label("avg_price"),
        func.max(rows.c.price).label("max_price"),
        func.sum(case((current, rows.c.price), else_=0)).label("current_volume"),
        func.sum(case((current, 1), else_=0)).label("current_count"),
        func.sum(case((prior, rows.c.price), else_=0)).label("prior_volume"),
    ).group_by(rows.c.card_id).subquery()


def observation_windows(timeframe, now):
    # Define current and prior windows for period-over-period momentum
    if timeframe == "24h":
        cur_start: datetime | None = now - timedelta(hours=24)
        cur_end: datetime | None = now
        prior_start: datetime | None = now - timedelta(hours=48)
        prior_end: datetime | None = now - timedelta(hours=24)
    elif timeframe == "7d":
        cur_start = now - timedelta(days=7)
        cur_end = now
        prior_start = now - timedelta(days=14)
        prior_end = now - timedelta(days=7)
    elif timeframe == "30d":
        cur_start = now - timedelta(days=30)
        cur_end = now
        prior_start = now - timedelta(days=60)
        prior_end = now - timedelta(days=30)
    elif timeframe == "2026_ytd":
        cur_start = datetime(2026, 1, 1, tzinfo=UTC)
        cur_end = now
        prior_start = now - timedelta(days=30)
        prior_end = now
    else:  # all_time
        cur_start = None
        cur_end = None
        prior_start = now - timedelta(days=30)
        prior_end = now

    return cur_start, cur_end, prior_start, prior_end


def dashboard_observation_snapshot(db, timeframe, now):
    """Request-scoped rows shared by all default Trending sections."""
    from app.models import Card, Set
    stats = card_observation_stats(*observation_windows(timeframe, now))
    return db.execute(select(
        Card.id, Card.name, Card.number, Card.rarity,
        Set.id.label("set_id"), Set.name.label("set_name"),
        func.coalesce(stats.c.obs_cnt, 0).label("obs_cnt"),
        stats.c.avg_price, stats.c.max_price, stats.c.total_price, stats.c.price_count,
        stats.c.current_volume, stats.c.current_count, stats.c.prior_volume,
    ).join(Set, Card.set_id == Set.id).outerjoin(stats, stats.c.card_id == Card.id)
      .where(Card.name.not_ilike("%code card%"))
      .execution_options(yield_per=512)).all()
