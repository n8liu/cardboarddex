import argparse
import hashlib
import logging
from pathlib import Path
import re
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

# Ensure backend root is in sys.path when executed as a direct script
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import httpx
from celery import shared_task
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload
from app.common.formatters import (
    parse_iso_datetime as _parse_datetime,
    to_decimal as _decimal,
)
from app.config import get_settings
from app.database import SessionLocal
from app.ebay import EbayClient, EbayConfigurationError
from app.models import Card, PriceObservation, ProviderCardState, RawEbayListing, Set
from app.providers import ProviderRequestLimitExceeded
from parsers.title_matcher import parse_ebay_title

logger = logging.getLogger(__name__)
POPULAR_NAMES = ("Charizard", "Blastoise", "Venusaur", "Pikachu", "Lugia", "Umbreon", "Gengar", "Mewtwo", "Rayquaza")


def _state(
    session: Session,
    card_id: str,
    provider: str,
    status: str,
    payload: dict[str, Any],
    provider_card_id: str | None = None,
    method: str | None = None,
) -> None:
    existing = session.scalar(
        select(ProviderCardState).where(
            ProviderCardState.card_id == card_id, ProviderCardState.provider == provider
        )
    )
    if existing is None:
        existing = ProviderCardState(card_id=card_id, provider=provider, match_status=status)
        session.add(existing)
    existing.provider_card_id = provider_card_id
    existing.match_status = status
    existing.match_method = method
    existing.payload = payload
    existing.last_synced_at = datetime.now(UTC)


def _observation(
    session: Session,
    *,
    card_id: str,
    provider: str,
    provider_card_id: str,
    variant_id: str,
    price: Any,
    condition: str | None = None,
    printing: str | None = None,
    grading_company: str | None = None,
    grade: Any = None,
    currency: str = "USD",
    provider_updated_at: datetime | None = None,
    payload: dict[str, Any] | None = None,
) -> bool:
    amount = _decimal(price)
    if amount is None or amount <= 0:
        return False
    timestamp_key = (provider_updated_at or datetime.now(UTC)).date().isoformat()
    raw_key = "|".join((provider, card_id, provider_card_id, variant_id, timestamp_key, str(amount)))
    fingerprint = hashlib.sha256(raw_key.encode()).hexdigest()
    pending_fingerprints = session.info.setdefault("price_observation_fingerprints", set())
    if fingerprint in pending_fingerprints:
        return False
    if session.scalar(select(PriceObservation.id).where(PriceObservation.fingerprint == fingerprint)):
        pending_fingerprints.add(fingerprint)
        return False
    parsed_grade = _decimal(grade)
    session.add(
        PriceObservation(
            fingerprint=fingerprint,
            card_id=card_id,
            provider=provider,
            provider_card_id=provider_card_id,
            variant_id=variant_id,
            condition=condition,
            printing=printing,
            grading_company=grading_company,
            grade=parsed_grade,
            price=amount,
            currency=currency[:3].upper(),
            provider_updated_at=provider_updated_at,
            observed_at=datetime.now(UTC),
            payload=payload,
        )
    )
    pending_fingerprints.add(fingerprint)
    return True


def _record_raw_listing(
    session: Session,
    item_id: str,
    card_id: str,
    title: str,
    price: Decimal | None,
    currency: str,
    item_url: str | None,
    seller_feedback: int | None,
    listing_date: datetime | None,
    match_status: str,
    rejection_reason: str | None,
    grading_company: str | None,
    grade: Decimal | None,
    payload: dict[str, Any],
) -> RawEbayListing:
    existing = session.scalar(select(RawEbayListing).where(RawEbayListing.ebay_item_id == item_id))
    if existing is None:
        existing = RawEbayListing(
            ebay_item_id=item_id,
            card_id=card_id,
            title=title,
            price=price,
            currency=currency,
            item_url=item_url,
            seller_feedback_score=seller_feedback,
            listing_date=listing_date,
            match_status=match_status,
            rejection_reason=rejection_reason,
            grading_company=grading_company,
            grade=grade,
            raw_payload=payload,
        )
        session.add(existing)
    else:
        existing.card_id = card_id
        existing.title = title
        existing.price = price
        existing.currency = currency
        existing.item_url = item_url
        existing.seller_feedback_score = seller_feedback
        existing.listing_date = listing_date
        existing.match_status = match_status
        existing.rejection_reason = rejection_reason
        existing.grading_company = grading_company
        existing.grade = grade
        existing.raw_payload = payload
    return existing


def clean_query_term(text: str) -> str:
    """Sanitize card and set names for eBay keyword queries."""
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", " ", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(item) for item in obj]
    return obj


def _collect_ebay_for_card(
    session: Session,
    card: Card,
    client: EbayClient,
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Search eBay Browse API for listings matching the given card,
    run title resolution, record raw listings, and generate price observations.
    """
    set_name = card.set.name if card.set else ""
    is_japanese = bool(card.set and card.set.series == "Pokemon Japan")
    query = f"{clean_query_term(card.name)} {clean_query_term(card.number)} {clean_query_term(set_name)}".strip()
    logger.info("Collecting eBay comps card_id=%s name=%s number=%s query=%s is_japanese=%s", card.id, card.name, card.number, query, is_japanese)

    raw_items = client.search_item_summaries(query, limit=30)
    matched_count = 0
    observations_created = 0
    all_results: list[dict[str, Any]] = []

    is_sealed = (card.rarity is None or card.rarity == "") and "code card" not in card.name.lower()
    for item in raw_items:
        item_id = str(item.get("itemId") or "")
        if not item_id:
            continue
        title = str(item.get("title") or "").strip()
        price_dict = item.get("price") if isinstance(item.get("price"), dict) else {}
        price_val = _decimal(price_dict.get("value"))
        currency = str(price_dict.get("currency") or "USD")
        item_url = str(item.get("itemWebUrl") or "")
        seller = item.get("seller") if isinstance(item.get("seller"), dict) else {}
        feedback = int(seller.get("feedbackScore", 0)) if seller.get("feedbackScore") else None
        item_date = _parse_datetime(item.get("itemCreationDate") or item.get("itemEndDate"))

        # Parse title conservatively
        match_result = parse_ebay_title(
            title,
            target_card_name=card.name,
            target_card_number=card.number or "",
            target_set_name=set_name,
            is_target_sealed=is_sealed,
            is_target_japanese=is_japanese,
        )

        all_results.append({
            "item_id": item_id,
            "title": title,
            "match_status": match_result.status,
            "reason": match_result.rejection_reason,
            "grade": str(match_result.grade) if match_result.grade is not None else None,
            "company": match_result.grading_company,
        })

        if not dry_run:
            _record_raw_listing(
                session,
                item_id=item_id,
                card_id=card.id,
                title=title,
                price=price_val,
                currency=currency,
                item_url=item_url,
                seller_feedback=feedback,
                listing_date=item_date,
                match_status=match_result.status,
                rejection_reason=match_result.rejection_reason,
                grading_company=match_result.grading_company,
                grade=match_result.grade,
                payload=_json_safe(item),
            )

        if match_result.status == "matched":
            matched_count += 1
            if dry_run:
                observations_created += 1
            elif price_val is not None:
                if is_sealed:
                    variant_id = f"ebay:{card.id}:sealed"
                    condition = match_result.condition or "Sealed"
                    printing = match_result.printing or "Sealed"
                    grading_company = None
                    grade = None
                else:
                    slab_part = match_result.grading_company or "raw"
                    grade_part = str(match_result.grade) if match_result.grade is not None else (match_result.condition or "standard")
                    variant_id = f"ebay:{card.id}:{slab_part}:{grade_part}".lower()
                    condition = match_result.condition
                    printing = match_result.printing
                    grading_company = match_result.grading_company
                    grade = match_result.grade

                created = _observation(
                    session,
                    card_id=card.id,
                    provider="ebay",
                    provider_card_id=item_id,
                    variant_id=variant_id,
                    price=price_val,
                    condition=condition,
                    printing=printing,
                    grading_company=grading_company,
                    grade=grade,
                    currency=currency,
                    provider_updated_at=item_date,
                    payload=_json_safe({"item": item, "title": title, "match": match_result.__dict__}),
                )
                if created:
                    observations_created += 1

    if not dry_run:
        _state(
            session,
            card_id=card.id,
            provider="ebay",
            status="matched" if matched_count > 0 else "unmatched",
            payload=_json_safe({"query": query, "total_raw": len(raw_items), "matched": matched_count, "results": all_results}),
            provider_card_id=card.id,
            method="ebay_browse_search",
        )

    return len(raw_items), observations_created


def _cards_for_ebay_collection(
    session: Session,
    limit: int,
    specific_card_id: str | None = None,
    card_ids: list[str] | None = None,
) -> list[Card]:
    if specific_card_id:
        card = session.get(Card, specific_card_id, options=[joinedload(Card.set)])
        return [card] if card else []
    if card_ids is not None:
        if not card_ids:
            return []
        stmt = (
            select(Card)
            .options(joinedload(Card.set))
            .where(Card.id.in_(card_ids))
            .limit(limit)
        )
        return list(session.scalars(stmt).unique())

    latest_ebay = select(
        ProviderCardState.card_id,
        func.max(ProviderCardState.last_synced_at).label("last_sync"),
    ).where(ProviderCardState.provider == "ebay").group_by(ProviderCardState.card_id).subquery()

    priority = case((Card.name.in_(POPULAR_NAMES), 0), else_=1)
    return list(session.scalars(
        select(Card)
        .options(joinedload(Card.set))
        .outerjoin(latest_ebay, latest_ebay.c.card_id == Card.id)
        .where(
            Card.name.not_ilike("%code card%"),
            or_(
                (Card.number.is_not(None) & (Card.number != "None") & Card.rarity.is_not(None) & (Card.rarity != "")),
                (Card.rarity.is_(None) | (Card.rarity == "")),
            ),
        )
        .order_by(latest_ebay.c.last_sync.asc().nullsfirst(), priority, Card.name, Card.id)
        .limit(limit)
    ))


def run_ebay_price_collection(
    session: Session,
    limit: int | None = None,
    card_id: str | None = None,
    card_ids: list[str] | None = None,
    ebay_client: EbayClient | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    configured_limit = limit if limit is not None else (len(card_ids) if card_ids is not None else get_settings().price_collection_card_limit)
    client = ebay_client or EbayClient()
    result = {"cards": 0, "raw_listings": 0, "ebay_observations": 0, "provider_errors": 0}

    cards = _cards_for_ebay_collection(session, configured_limit, specific_card_id=card_id, card_ids=card_ids)
    for card in cards:
        result["cards"] += 1
        try:
            raw_count, obs_count = _collect_ebay_for_card(session, card, client, dry_run=dry_run)
            result["raw_listings"] += raw_count
            result["ebay_observations"] += obs_count
            if not dry_run:
                session.commit()
        except (
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
            ProviderRequestLimitExceeded,
            EbayConfigurationError,
            SQLAlchemyError,
        ) as exc:
            if not dry_run:
                session.rollback()
                session.info.pop("price_observation_fingerprints", None)
            result["provider_errors"] += 1
            logger.exception(
                "eBay price collection failed card_id=%s error=%s: %s",
                card.id,
                type(exc).__name__,
                exc,
            )

    logger.info("eBay price collection complete result=%s", result)
    return result


@shared_task(name="jobs.collect_ebay_prices.collect_ebay_prices", autoretry_for=(), max_retries=0)
def collect_ebay_prices() -> dict[str, int]:
    with SessionLocal() as session:
        return run_ebay_price_collection(session)


def _find_cards_by_query(session: Session, query_text: str, limit: int = 10) -> list[Card]:
    clean = query_text.strip()
    if not clean:
        return []
    # 1. Exact ID
    card = session.get(Card, clean, options=[joinedload(Card.set)])
    if card:
        return [card]
    # 2. Match all tokens across Card.name, Set.name, or Card.number
    tokens = clean.split()
    stmt = (
        select(Card)
        .options(joinedload(Card.set))
        .join(Set, Card.set_id == Set.id)
        .where(
            Card.name.not_ilike("%code card%"),
        )
    )
    for token in tokens:
        pat = f"%{token}%"
        stmt = stmt.where((Card.name.ilike(pat)) | (Set.name.ilike(pat)) | (Card.number == token))
    return list(session.scalars(stmt.order_by(Card.name, Card.id).limit(limit)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect eBay comps for Pokémon cards")
    parser.add_argument("query", nargs="*", help="Optional card ID or name search (e.g. 'base1-4' or 'Charizard Base Set')")
    parser.add_argument("--limit", type=int, help="Limit number of cards to process")
    parser.add_argument("--card-id", type=str, help="Process specific card ID")
    parser.add_argument("--dry-run", action="store_true", help="Run without persisting database changes")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    with SessionLocal() as session:
        card_id = args.card_id
        if not card_id and args.query:
            query_str = " ".join(args.query).strip()
            matching_cards = _find_cards_by_query(session, query_str, limit=args.limit or 5)
            if matching_cards:
                print(f"Found {len(matching_cards)} matching card(s) for '{query_str}':")
                for c in matching_cards:
                    print(f"  - [{c.id}] {c.name} #{c.number} ({c.set.name if c.set else ''})")
                client = EbayClient()
                total_res = {"cards": 0, "raw_listings": 0, "ebay_observations": 0, "provider_errors": 0}
                for c in matching_cards:
                    try:
                        raw_count, obs_count = _collect_ebay_for_card(session, c, client, dry_run=args.dry_run)
                        total_res["cards"] += 1
                        total_res["raw_listings"] += raw_count
                        total_res["ebay_observations"] += obs_count
                        if not args.dry_run:
                            session.commit()
                    except Exception as exc:
                        if not args.dry_run:
                            session.rollback()
                        total_res["provider_errors"] += 1
                        logger.exception("Failed collecting eBay comps for card=%s error=%s: %s", c.id, type(exc).__name__, exc)
                print("Result:", total_res)
                return
            else:
                print(f"No cards found matching query: '{query_str}'")
                return

        result = run_ebay_price_collection(
            session,
            limit=args.limit,
            card_id=card_id,
            dry_run=args.dry_run,
        )
        print("Result:", result)


if __name__ == "__main__":
    main()
