"""Stored collection totals shared by the homepage and unfiltered Live Comps."""
import logging

from sqlalchemy import func, select
from app.models import Card, PriceObservation, Set

logger = logging.getLogger(__name__)
from app.services.listing_quality import eligible_observation

COUNT_KEY = "cardboarddex:live_updates:total_count:identity-v1"


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
