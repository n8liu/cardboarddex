"""Shared, fail-closed eligibility for eBay asking-price observations."""
import hashlib
import json
from datetime import UTC, datetime, timedelta
from statistics import median
from sqlalchemy import and_, exists, or_, select
from app.models import ListingAssessment, PriceObservation
from parsers.title_matcher import parse_ebay_title, is_sealed_product, listing_specifics_issue

MATCHER_VERSION = "identity-v1"


def eligible_observation():
    """Correlated SQL predicate: apply before ranking, aggregating or paginating."""
    from app.services.price_sources import public_observation
    return and_(public_observation(), or_(~PriceObservation.provider.ilike("%ebay%"), exists(select(1).where(
        ListingAssessment.fingerprint == PriceObservation.payload["assessment_fingerprint"].as_string(),
        ListingAssessment.card_id == PriceObservation.card_id,
        ListingAssessment.item_id == PriceObservation.provider_card_id,
        ListingAssessment.version == MATCHER_VERSION,
        ListingAssessment.status == "matched",
    ))))


def assess_text(db, card, item, *, supersede=True):
    sealed = is_sealed_product(card.name)
    result = parse_ebay_title(str(item.get("title") or ""), card.name, card.number or "",
        card.set.name if card.set else "", is_target_sealed=sealed,
        is_target_japanese=bool(card.set and card.set.series == "Pokemon Japan"),
        strict=True, target_printed_total=card.printed_total or (card.set.printed_total if card.set else None))
    issue = listing_specifics_issue(item, card.number, card.set.name if card.set else "", result,
                                   bool(card.set and card.set.series == "Pokemon Japan"))
    if issue:
        result.status, result.rejection_reason = "rejected", issue
    # Unknown finishes must not silently enter a known printing cohort.
    if not sealed and result.printing == "Standard":
        result.printing = None
    if result.condition == "Raw":
        result.condition = None
    # Price-only changes do not change product identity. Titles, images, seller,
    # variations and item specifics do invalidate the existing assessment.
    target = [card.id, card.name, card.number, card.image_url, card.rarity,
              card.printed_total, card.set.name if card.set else None,
              card.set.printed_total if card.set else None]
    identity = {key: item.get(key) for key in ("itemId", "title", "image", "additionalImages", "localizedAspects", "condition", "conditionId", "itemGroupType", "itemGroupHref", "buyingOptions")}
    identity["seller"] = (item.get("seller") or {}).get("username")
    fingerprint = hashlib.sha256(json.dumps([MATCHER_VERSION, target, identity], sort_keys=True, default=str).encode()).hexdigest()
    if supersede:
        previous = db.scalars(select(ListingAssessment).where(ListingAssessment.card_id == card.id,
            ListingAssessment.item_id == str(item.get("itemId") or ""), ListingAssessment.fingerprint != fingerprint))
        for old in previous:
            old.status = "superseded"
            old.reasons = ["listing_identity_changed"]
    assessment = db.get(ListingAssessment, fingerprint)
    if assessment is not None and assessment.image_status == "matched" and assessment.checked_at:
        checked = assessment.checked_at.replace(tzinfo=UTC) if assessment.checked_at.tzinfo is None else assessment.checked_at
        if checked < datetime.now(UTC) - timedelta(days=7):
            assessment.status = assessment.image_status = "pending"
            assessment.attempts = 0
            assessment.checked_at = None
            assessment.reasons = ["image_recheck_due"]
    if assessment is not None and assessment.status == "superseded" and supersede:
        assessment.status = "pending" if assessment.text_status == "matched" and assessment.image_status != "not_applicable" else assessment.text_status
        assessment.image_status = "pending" if assessment.image_status != "not_applicable" else "not_applicable"
        assessment.attempts = 0
        assessment.checked_at = None
    if assessment is None:
        image_required = not sealed and not result.is_graded
        assessment = ListingAssessment(fingerprint=fingerprint, card_id=card.id,
            item_id=str(item.get("itemId") or ""), version=MATCHER_VERSION,
            text_status=result.status, image_status="pending" if image_required else "not_applicable",
            status=("pending" if image_required else "matched") if result.status == "matched" else result.status,
            reasons=[result.rejection_reason] if result.rejection_reason else [],
            evidence={"printing": result.printing, "condition": result.condition,
                      "seller": str((item.get("seller") or {}).get("username") or "").casefold(),
                      "reference_url": card.image_url}, source=item, attempts=0)
        db.add(assessment)
        db.flush()
    return assessment, result


def listing_summary(rows, assessments, printing, condition):
    now = datetime.now(UTC)
    latest = {}
    for row in rows:
        stamp = row.observed_at.replace(tzinfo=UTC) if row.observed_at.tzinfo is None else row.observed_at
        if not (now - timedelta(days=7) <= stamp <= now) or row.currency != "USD" or row.grading_company or row.price <= 0:
            continue
        if row.printing != printing or row.condition != condition:
            continue
        key = (row.provider, row.provider_card_id)
        if key not in latest or row.observed_at > latest[key].observed_at:
            latest[key] = row
    prices = [float(row.price) for row in latest.values()]
    sellers = {assessments[(row.payload or {}).get("assessment_fingerprint")].evidence.get("seller")
               for row in latest.values() if (row.payload or {}).get("assessment_fingerprint") in assessments}
    sellers.discard(None)
    sellers.discard("")
    enough = len(prices) >= 3 and len(sellers) >= 2
    return dict(lowest_matched_price=min(prices) if prices else None,
        avg_listing_price=sum(prices) / len(prices) if enough else None,
        median_listing_price=median(prices) if enough else None,
        listing_sample_count=len(prices), listing_seller_count=len(sellers))
