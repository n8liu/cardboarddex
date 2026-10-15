"""Stored collection totals shared by the homepage and unfiltered Live Comps."""
import logging

from sqlalchemy import func, select
from app.models import Card, PriceObservation, Set

logger = logging.getLogger(__name__)
COUNT_KEY = "cardboarddex:live_updates:total_count"


def live_observation_count(db, redis=None):
    if redis is not None:
        try:
            cached = redis.get(COUNT_KEY)
            if cached is not None:
                return int(cached)
        except Exception as exc:
            logger.warning("Live observation count cache read failed error=%s: %s", type(exc).__name__, exc)
    total = db.scalar(select(func.count()).select_from(PriceObservation)
                      .join(Card, PriceObservation.card_id == Card.id).join(Set, Card.set_id == Set.id)) or 0
    if redis is not None:
        try:
            redis.setex(COUNT_KEY, 60, str(total))
        except Exception as exc:
            logger.warning("Live observation count cache write failed error=%s: %s", type(exc).__name__, exc)
    return total
