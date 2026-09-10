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
from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.database import SessionLocal
from app.models import Card, PriceObservation, ProviderCardState
from app.providers import ProviderRequestLimitExceeded
from app.tcgapi import TCGAPIClient, TCGAPIConfigurationError

logger = logging.getLogger(__name__)
POPULAR_NAMES = ("Charizard", "Blastoise", "Venusaur", "Pikachu", "Lugia", "Umbreon")


def normalize_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def normalize_number(value: Any) -> str:
    first = str(value or "").split("/", 1)[0].strip().lower()
    return first.lstrip("0") or "0"


def select_exact_candidates(
    items: list[dict[str, Any]], card: Card, set_name: str, *,
    name_field: str, set_field: str, number_field: str,
) -> list[dict[str, Any]]:
    expected = (normalize_text(card.name), normalize_text(set_name), normalize_number(card.number))
    results: list[dict[str, Any]] = []
    for item in items:
        raw_set = item.get(set_field)
        if isinstance(raw_set, dict):
            raw_set = raw_set.get("name")
        actual = (
            normalize_text(item.get(name_field)), normalize_text(raw_set),
            normalize_number(item.get(number_field)),
        )
        if actual == expected:
            results.append(item)
    return results


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            logger.warning("Provider timestamp invalid value=%s error=%s: %s", value, type(exc).__name__, exc)
    return None


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        logger.warning("Provider price invalid value=%s error=%s: %s", value, type(exc).__name__, exc)
        return None


def _state(session: Session, card_id: str, provider: str, status: str,
           payload: dict[str, Any], provider_card_id: str | None = None,
           method: str | None = None) -> None:
    existing = session.scalar(select(ProviderCardState).where(
        ProviderCardState.card_id == card_id, ProviderCardState.provider == provider
    ))
    if existing is None:
        existing = ProviderCardState(card_id=card_id, provider=provider, match_status=status)
        session.add(existing)
    existing.provider_card_id = provider_card_id
    existing.match_status = status
    existing.match_method = method
    existing.payload = payload
    existing.last_synced_at = datetime.now(UTC)


def _observation(session: Session, *, card_id: str, provider: str,
                 provider_card_id: str, variant_id: str, price: Any,
                 condition: str | None = None, printing: str | None = None,
                 grading_company: str | None = None, grade: Any = None,
                 currency: str = "USD", provider_updated_at: datetime | None = None,
                 payload: dict[str, Any] | None = None) -> bool:
    amount = _decimal(price)
    if amount is None:
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
    session.add(PriceObservation(
        fingerprint=fingerprint, card_id=card_id, provider=provider,
        provider_card_id=provider_card_id, variant_id=variant_id,
        condition=condition, printing=printing, grading_company=grading_company,
        grade=parsed_grade, price=amount, currency=currency[:3].upper(),
        provider_updated_at=provider_updated_at, observed_at=datetime.now(UTC), payload=payload,
    ))
    pending_fingerprints.add(fingerprint)
    return True


def _collect_tcgapi(session: Session, card: Card, set_name: str, client: TCGAPIClient) -> int:
    try:
        card_payload = client.get_card(card.id)
    except httpx.HTTPStatusError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            logger.info(
                "TCG API card not found card_id=%s name=%s set=%s status=404; marking unmatched",
                card.id,
                card.name,
                set_name,
            )
            _state(
                session,
                card.id,
                "tcgapi",
                "unmatched",
                {"reason": "card_not_found_404"},
            )
            return 0
        logger.error(
            "TCG API get_card failed card_id=%s status=%s error=%s: %s",
            card.id,
            exc.response.status_code if exc.response is not None else None,
            type(exc).__name__,
            exc,
        )
        raise

    item = card_payload.get("data")
    if not isinstance(item, dict):
        _state(
            session,
            card.id,
            "tcgapi",
            "unmatched",
            {"reason": "card_not_found", "response": card_payload},
        )
        return 0

    matches = select_exact_candidates(
        [item],
        card,
        set_name,
        name_field="name",
        set_field="set_name",
        number_field="number",
    )
    if not matches:
        _state(
            session,
            card.id,
            "tcgapi",
            "unmatched",
            {"reason": "catalog_identity_mismatch", "response": card_payload},
        )
        return 0

    try:
        prices_payload = client.get_card_prices(card.id)
    except httpx.HTTPStatusError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            logger.info(
                "TCG API price data not found card_id=%s name=%s set=%s status=404; marking no_price_data",
                card.id,
                card.name,
                set_name,
            )
            _state(
                session,
                card.id,
                "tcgapi",
                "no_price_data",
                {"card": card_payload, "reason": "price_data_not_found"},
                card.id,
                "canonical_tcgapi_id",
            )
            return 0
        logger.error(
            "TCG API get_card_prices failed card_id=%s status=%s error=%s: %s",
            card.id,
            exc.response.status_code if exc.response is not None else None,
            type(exc).__name__,
            exc,
        )
        raise

    raw_prices = prices_payload.get("data")
    if isinstance(raw_prices, dict):
        prices = [raw_prices]
    elif isinstance(raw_prices, list):
        prices = [price for price in raw_prices if isinstance(price, dict)]
    else:
        prices = []

    _state(
        session,
        card.id,
        "tcgapi",
        "matched",
        {"card": card_payload, "prices": prices_payload},
        card.id,
        "canonical_tcgapi_id",
    )
    inserted = 0
    for price in prices:
        printing = str(price.get("printing") or "Standard")
        inserted += _observation(
            session,
            card_id=card.id,
            provider="tcgapi",
            provider_card_id=card.id,
            variant_id=f"{card.id}:{normalize_text(printing) or 'standard'}",
            price=price.get("market_price"),
            printing=printing,
            currency="USD",
            provider_updated_at=_parse_datetime(price.get("last_updated_at")),
            payload=price,
        )
    return inserted


def _cards_for_collection(session: Session, limit: int) -> list[Card]:
    latest = select(
        ProviderCardState.card_id, func.max(ProviderCardState.last_synced_at).label("last_sync")
    ).group_by(ProviderCardState.card_id).subquery()
    priority = case((Card.name.in_(POPULAR_NAMES), 0), else_=1)
    return list(session.scalars(
        select(Card).options(joinedload(Card.set)).outerjoin(latest, latest.c.card_id == Card.id)
        .where(Card.number.is_not(None), Card.number != "None")
        .order_by(latest.c.last_sync.asc().nullsfirst(), priority, Card.name, Card.id).limit(limit)
    ))


_BULK_PRICES_SUPPORTED: bool = True


def run_price_collection(
    session: Session,
    limit: int | None = None,
    tcgapi: TCGAPIClient | None = None,
) -> dict[str, int]:
    global _BULK_PRICES_SUPPORTED
    configured_limit = limit if limit is not None else get_settings().price_collection_card_limit
    tcgapi_client = tcgapi or TCGAPIClient()
    result = {"cards": 0, "tcgapi_observations": 0, "provider_errors": 0}
    candidates = _cards_for_collection(session, configured_limit)
    if not candidates:
        return result

    # Check if client supports bulk price lookups (GET /bulk/prices)
    if _BULK_PRICES_SUPPORTED and hasattr(tcgapi_client, "get_bulk_prices"):
        chunk_size = 100
        for i in range(0, len(candidates), chunk_size):
            chunk = candidates[i : i + chunk_size]
            card_map = {card.id: card for card in chunk}
            try:
                bulk_res = tcgapi_client.get_bulk_prices(list(card_map.keys()))
                bulk_items = bulk_res.get("data") if isinstance(bulk_res, dict) else None
                if not isinstance(bulk_items, list):
                    bulk_items = []

                prices_by_card: dict[str, list[dict[str, Any]]] = {}
                for item in bulk_items:
                    if isinstance(item, dict) and item.get("card_id"):
                        prices_by_card.setdefault(str(item["card_id"]), []).append(item)

                processed_ids: set[str] = set()
                for cid, prices in prices_by_card.items():
                    card = card_map.get(cid)
                    if not card:
                        continue
                    processed_ids.add(cid)
                    result["cards"] += 1
                    _state(
                        session,
                        card.id,
                        "tcgapi",
                        "matched",
                        {"prices": {"data": prices}},
                        card.id,
                        "canonical_tcgapi_id",
                    )
                    for price in prices:
                        printing = str(price.get("printing") or "Standard")
                        result["tcgapi_observations"] += _observation(
                            session,
                            card_id=card.id,
                            provider="tcgapi",
                            provider_card_id=card.id,
                            variant_id=f"{card.id}:{normalize_text(printing) or 'standard'}",
                            price=price.get("market_price"),
                            printing=printing,
                            currency="USD",
                            provider_updated_at=_parse_datetime(price.get("last_updated_at")),
                            payload=price,
                        )

                # For any card in chunk not returned in bulk, fall back to individual fetch
                for card in chunk:
                    if card.id not in processed_ids:
                        result["cards"] += 1
                        result["tcgapi_observations"] += _collect_tcgapi(
                            session, card, card.set.name, tcgapi_client
                        )
                session.commit()
            except httpx.HTTPStatusError as exc:
                session.rollback()
                session.info.pop("price_observation_fingerprints", None)
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code in (403, 404):
                    _BULK_PRICES_SUPPORTED = False
                    logger.warning(
                        "TCG API bulk prices endpoint unavailable or tier restricted status=%s error=%s: %s; "
                        "disabling bulk lookups and falling back to individual card pricing",
                        status_code,
                        type(exc).__name__,
                        exc,
                    )
                    # Process remaining cards individually
                    for card in chunk:
                        result["cards"] += 1
                        try:
                            result["tcgapi_observations"] += _collect_tcgapi(
                                session, card, card.set.name, tcgapi_client
                            )
                            session.commit()
                        except (
                            httpx.HTTPError,
                            KeyError,
                            TypeError,
                            ValueError,
                            ProviderRequestLimitExceeded,
                            TCGAPIConfigurationError,
                            SQLAlchemyError,
                        ) as card_exc:
                            session.rollback()
                            session.info.pop("price_observation_fingerprints", None)
                            result["provider_errors"] += 1
                            logger.exception(
                                "Price collection provider failed provider=tcgapi card_id=%s error=%s: %s",
                                card.id,
                                type(card_exc).__name__,
                                card_exc,
                            )
                else:
                    result["provider_errors"] += len(chunk)
                    logger.exception(
                        "Bulk price collection HTTP error chunk_size=%s status=%s error=%s: %s",
                        len(chunk),
                        status_code,
                        type(exc).__name__,
                        exc,
                    )
            except (
                httpx.HTTPError,
                KeyError,
                TypeError,
                ValueError,
                ProviderRequestLimitExceeded,
                TCGAPIConfigurationError,
                SQLAlchemyError,
            ) as exc:
                session.rollback()
                session.info.pop("price_observation_fingerprints", None)
                result["provider_errors"] += len(chunk)
                logger.exception(
                    "Bulk price collection failed chunk_size=%s error=%s: %s",
                    len(chunk),
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
    else:
        for card in candidates:
            result["cards"] += 1
            try:
                result["tcgapi_observations"] += _collect_tcgapi(
                    session, card, card.set.name, tcgapi_client
                )
                session.commit()
            except (
                httpx.HTTPError,
                KeyError,
                TypeError,
                ValueError,
                ProviderRequestLimitExceeded,
                TCGAPIConfigurationError,
                SQLAlchemyError,
            ) as exc:
                session.rollback()
                session.info.pop("price_observation_fingerprints", None)
                result["provider_errors"] += 1
                logger.exception(
                    "Price collection provider failed provider=tcgapi card_id=%s error=%s: %s",
                    card.id,
                    type(exc).__name__,
                    exc,
                )
    logger.info("Price collection complete result=%s", result)
    return result


@shared_task(name="jobs.collect_prices.collect_prices", autoretry_for=(), max_retries=0)
def collect_prices() -> dict[str, int]:
    with SessionLocal() as session:
        return run_price_collection(session)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    with SessionLocal() as session:
        print(run_price_collection(session, limit=args.limit))


if __name__ == "__main__":
    main()
