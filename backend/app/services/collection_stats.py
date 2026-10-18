"""Stored collection totals shared by the homepage and unfiltered Live Comps."""
import logging

from sqlalchemy import func, select, case, and_
from app.models import Card, PriceObservation, Set, ListingAssessment

logger = logging.getLogger(__name__)
from app.services.listing_quality import eligible_observation

COUNT_KEY = "cardboarddex:live_updates:total_count:identity-v1"


def live_observation_totals(db):
    """Exact KPIs without correlated assessment probes across full history."""
    from app.services.price_sources import public_observation
    from app.services.listing_quality import MATCHER_VERSION

    # The provider-feed covering index contains provider and grading_company.
    non_listing = db.execute(select(
        func.count(case((PriceObservation.provider == "tcgapi", 1))),
        func.count(PriceObservation.grading_company),
    ).where(PriceObservation.provider.not_ilike("%ebay%"), public_observation())).one()

    # Assessment fingerprints are unique, so this join cannot multiply rows.
    # Keep all identity/version predicates from eligible_observation; joining on
    # a matched fingerprint alone would permit evidence for the wrong product.
    matched = db.execute(select(
        func.count(case((PriceObservation.provider == "ebay", 1))),
        func.count(PriceObservation.grading_company),
    ).select_from(ListingAssessment).join(PriceObservation, and_(
        PriceObservation.card_id == ListingAssessment.card_id,
        PriceObservation.provider_card_id == ListingAssessment.item_id,
        PriceObservation.payload["assessment_fingerprint"].as_string() == ListingAssessment.fingerprint,
    )).where(
        ListingAssessment.version == MATCHER_VERSION,
        ListingAssessment.status == "matched",
        PriceObservation.provider.ilike("%ebay%"),
        public_observation(),
    )).one()
    return matched[0], non_listing[0], non_listing[1] + matched[1]


def live_observation_count(db, redis=None):
    from app.config import get_settings
    count_key = COUNT_KEY + (":ppt" if get_settings().ppt_primary_enabled else "")
    if redis is not None:
        try:
            cached = redis.get(count_key)
            if cached is not None:
                return int(cached)
        except Exception as exc:
            logger.warning("Live observation count cache read failed error=%s: %s", type(exc).__name__, exc)
    total = db.scalar(select(func.count()).select_from(PriceObservation)
                      .join(Card, PriceObservation.card_id == Card.id).join(Set, Card.set_id == Set.id).where(eligible_observation())) or 0
    if redis is not None:
        try:
            redis.setex(count_key, 60, str(total))
        except Exception as exc:
            logger.warning("Live observation count cache write failed error=%s: %s", type(exc).__name__, exc)
    return total
