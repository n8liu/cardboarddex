"""One feature-gated selection rule shared by stored-price consumers."""
from datetime import UTC, datetime, timedelta
from sqlalchemy import and_, case, exists, or_, select, false
from sqlalchemy.orm import aliased
from app.config import get_settings
from app.models import PriceObservation
from app.providers.ppt import PROVIDER


def public_observation():
    return PriceObservation.provider != PROVIDER if not get_settings().ppt_primary_enabled else PriceObservation.id.is_not(None)


def ppt_current(observation=PriceObservation):
    # A snapshot's last successful fetch may deliberately contain no current median.
    # Only the fingerprint of a current quote can be selected, never an older row.
    from app.models import PPTCurrentQuote
    return exists(select(PPTCurrentQuote.fingerprint).where(
        PPTCurrentQuote.fingerprint == observation.fingerprint,
        PPTCurrentQuote.price_date >= datetime.now(UTC).date() - timedelta(days=7),
    )).correlate(observation)


def market_observation():
    if not get_settings().ppt_primary_enabled:
        return PriceObservation.provider == "tcgapi"
    from app.models import PPTCurrentQuote
    other = aliased(PriceObservation)
    # Independent set, shared by both branches: do not re-probe historical rows
    # for every legacy observation in a broad catalog sort.
    preferred = (select(other.card_id, other.fingerprint)
        .join(PPTCurrentQuote, PPTCurrentQuote.fingerprint == other.fingerprint)
        .where(other.provider == PROVIDER,
               other.payload["primary"].as_boolean().is_(True),
               other.grading_company.is_(None), other.card_id.is_not(None),
               PPTCurrentQuote.price_date >= datetime.now(UTC).date() - timedelta(days=7))
        .correlate(None).cte())
    return or_(
        and_(PriceObservation.provider == PROVIDER,
             PriceObservation.fingerprint.in_(select(preferred.c.fingerprint))),
        and_(PriceObservation.provider == "tcgapi",
             PriceObservation.card_id.not_in(select(preferred.c.card_id))))


def source_priority():
    return case((PriceObservation.provider == PROVIDER, 0), else_=1)


def grading_observation():
    from app.services.listing_quality import eligible_observation
    if not get_settings().ppt_primary_enabled:
        return eligible_observation()
    # Current PPT medians take precedence. A mapped card with missing recent PSA
    # coverage stays unavailable instead of silently substituting asking prices.
    from app.models import PPTProduct
    mapped = exists(select(PPTProduct.id).where(PPTProduct.card_id == PriceObservation.card_id,
        PPTProduct.status == "matched", PPTProduct.last_success_at.is_not(None))).correlate(PriceObservation)
    return and_(eligible_observation(), or_(
        and_(PriceObservation.grading_company.is_(None), market_observation(),
             or_(PriceObservation.provider != PROVIDER, PriceObservation.condition.in_(["Near Mint", "NM"]))),
        and_(PriceObservation.grading_company.is_not(None),
             or_(and_(PriceObservation.provider == PROVIDER, ppt_current()),
                 and_(~mapped, PriceObservation.provider != PROVIDER)))))
