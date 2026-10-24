"""Robust prices from eBay asking listings.

An asking price is a seller's hope, not a sale: one listing can claim $17.5M for
a PSA 10 that sells for $200. A single newest listing must never set a price.
"""
import logging
from statistics import median, median_low

logger = logging.getLogger(__name__)

WINDOW_DAYS = 30
MAX_LISTINGS = 30
# Listings outside [median / BAND, median * BAND] are discarded before the final median.
BAND = 3.0
# A graded asking price above this multiple of the raw market price is not credible.
MAX_REFERENCE_MULTIPLE = 100.0


def robust_asking_price(prices: list[float], reference: float | None = None) -> float | None:
    """Median of asking prices after dropping outliers; None when nothing credible remains."""
    values = [p for p in prices if p is not None and p > 0]
    if not values:
        return None
    # The lower median is an actual listing, so an even count cannot be dragged
    # toward a wild ask; it always lies inside its own band.
    centre = median_low(values)
    result = median([p for p in values if centre / BAND <= p <= centre * BAND])
    if reference is not None and reference > 0 and result > reference * MAX_REFERENCE_MULTIPLE:
        logger.info("Asking price rejected price=%.2f reference=%.2f listings=%d",
                    result, reference, len(values))
        return None
    return result
