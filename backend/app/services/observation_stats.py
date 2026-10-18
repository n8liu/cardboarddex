"""Narrow, per-card history aggregates for analytics (not completed-sale claims)."""
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
