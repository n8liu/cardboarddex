"""Resumable checks and stored-data-only backfill. Never runs on page requests."""
import argparse
import logging
import time
from datetime import UTC, datetime, timedelta
import redis
from celery import shared_task
from sqlalchemy import select, or_, update, func, exists
from app.config import get_settings
from app.database import SessionLocal
from app.models import Card, ListingAssessment, PriceObservation
from app.services.listing_quality import assess_text, MATCHER_VERSION
from app.services.listing_images import compare_images

logger = logging.getLogger(__name__)


def backfill(db, limit=50):
    rows = db.scalars(select(PriceObservation).where(
        PriceObservation.provider.ilike("%ebay%"),
        ~exists(select(1).where(
            ListingAssessment.fingerprint == PriceObservation.payload["assessment_fingerprint"].as_string(),
            ListingAssessment.version == MATCHER_VERSION,
        )),
    ).order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc()).limit(limit))
    count = 0
    for row in rows:
        payload = row.payload or {}
        item = dict(payload.get("item") or {})
        item.setdefault("itemId", row.provider_card_id)
        item.setdefault("title", payload.get("title") or payload.get("listing_title") or "")
        assessment, _ = assess_text(db, db.get(Card, row.card_id), item, supersede=False)
        row.payload = {**payload, "assessment_fingerprint": assessment.fingerprint}
        count += 1
    db.commit()
    return count


def check_one(db, assessment):
    started = time.monotonic()
    now = datetime.now(UTC)
    card = db.get(Card, assessment.card_id)
    item = assessment.source
    images = [item.get("image"), *(item.get("additionalImages") or [])]
    urls = list(dict.fromkeys(image.get("imageUrl") for image in images if isinstance(image, dict) and image.get("imageUrl")))[:3]
    assessment.attempts += 1
    assessment.checked_at = now
    if not urls or not card.image_url:
        assessment.status = assessment.image_status = "uncertain"
        assessment.reasons = ["image_missing"]
        db.commit()
        return
    try:
        outcomes = [compare_images(card.image_url, url, card.number, card.printed_total or (card.set.printed_total if card.set else None)) for url in urls]
        # A contradictory image overrides any matching photo; back-only extras do not.
        chosen = next((x for x in outcomes if x[0] == "rejected"), None)
        chosen = chosen or next((x for x in outcomes if x[0] == "matched"), outcomes[0])
        status, reason, evidence = chosen
        if status == "matched" and not get_settings().listing_image_acceptance_enabled:
            status, reason = "uncertain", "image_acceptance_not_validated"
        assessment.status = assessment.image_status = status
        assessment.reasons = [reason]
        assessment.evidence = {**assessment.evidence, **evidence}
    except Exception as exc:
        logger.exception("Listing image check failed item_id=%s error=%s: %s", assessment.item_id, type(exc).__name__, exc)
        assessment.status = "pending" if assessment.attempts < 3 else "uncertain"
        assessment.image_status = "error"
        assessment.reasons = ["image_check_failed"]
    db.commit()
    logger.info("Listing assessment item_id=%s status=%s reasons=%s attempts=%s duration_seconds=%.3f",
                assessment.item_id, assessment.status, assessment.reasons, assessment.attempts, time.monotonic() - started)


@shared_task(name="jobs.check_listing_images.check_listing_images", soft_time_limit=110, time_limit=120)
def check_listing_images():
    settings = get_settings()
    if not settings.listing_image_checks_enabled:
        return {"disabled": True}
    client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    # Expiry exceeds task hard limit; a killed task cannot leave a permanent lock.
    lock = client.lock("cardboarddex:listing-images:lock", timeout=150, blocking_timeout=0)
    if not lock.acquire(blocking=False):
        return {"busy": True}
    try:
        with SessionLocal() as db:
            cutoff = datetime.now(UTC) - timedelta(minutes=15)
            db.execute(update(ListingAssessment).where(ListingAssessment.status == "pending",
                ListingAssessment.attempts >= 3, ListingAssessment.checked_at < cutoff).values(
                    status="uncertain", image_status="error", reasons=["image_retry_limit"]))
            db.commit()
            row = db.scalar(select(ListingAssessment).where(
                ListingAssessment.version == MATCHER_VERSION, ListingAssessment.status == "pending",
                ListingAssessment.attempts < 3,
                or_(ListingAssessment.checked_at.is_(None), ListingAssessment.checked_at < cutoff),
            ).order_by(ListingAssessment.checked_at.asc().nullsfirst(), ListingAssessment.created_at.desc()).limit(1))
            if row:
                # Persist attempt before expensive work so hard kills remain bounded.
                row.attempts += 1
                row.checked_at = datetime.now(UTC)
                db.commit()
                row.attempts -= 1
                check_one(db, row)
                return {"checked": 1, "status": row.status}
            return {"checked": 0}
    finally:
        if lock.owned():
            lock.release()


def assessment_report(db):
    counts = dict(db.execute(select(ListingAssessment.status, func.count()).group_by(ListingAssessment.status)).all())
    oldest = db.scalar(select(func.min(ListingAssessment.created_at)).where(ListingAssessment.status == "pending"))
    reasons = {}
    for values in db.scalars(select(ListingAssessment.reasons).where(ListingAssessment.status != "matched")):
        for reason in values:
            reasons[reason] = reasons.get(reason, 0) + 1
    unchecked = db.scalar(select(func.count()).select_from(PriceObservation).where(
        PriceObservation.provider.ilike("%ebay%"),
        ~exists(select(1).where(ListingAssessment.fingerprint == PriceObservation.payload["assessment_fingerprint"].as_string(),
                               ListingAssessment.version == MATCHER_VERSION)))) or 0
    return {"counts": counts, "unchecked_observations": unchecked,
            "oldest_pending_at": oldest.isoformat() if oldest else None, "reasons": reasons}


def retry_images(db, limit=50):
    rows = list(db.scalars(select(ListingAssessment).where(
        ListingAssessment.version == MATCHER_VERSION,
        ListingAssessment.text_status == "matched", ListingAssessment.status == "uncertain",
        ListingAssessment.image_status != "not_applicable",
    ).order_by(ListingAssessment.created_at.desc()).limit(limit)))
    for row in rows:
        row.status = row.image_status = "pending"
        row.attempts = 0
        row.checked_at = None
    db.commit()
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bounded stored eBay assessment maintenance; no provider API calls")
    parser.add_argument("--limit", type=int, default=50)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--report", action="store_true", help="Read-only assessment coverage and reasons")
    mode.add_argument("--retry-images", action="store_true", help="Return uncertain image checks to the pending queue")
    args = parser.parse_args()
    with SessionLocal() as db:
        limit = max(1, min(args.limit, 500))
        if args.report:
            print(assessment_report(db))
        elif args.retry_images:
            print({"queued": retry_images(db, limit)})
        else:
            print({"prepared": backfill(db, limit)})
