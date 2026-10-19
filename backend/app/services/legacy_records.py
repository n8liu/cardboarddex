"""Offline legacy record compatibility. No provider access or history retention pruning."""
import hashlib
import logging
from datetime import UTC, datetime
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Card, PriceObservation, ProviderCardState, MarketHistory, CatalogSnapshot
from app.common.formatters import normalize_card_number as normalize_number, normalize_text, parse_iso_datetime as _parse_datetime, to_decimal as _decimal
logger = logging.getLogger(__name__)

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
    existing.payload = {**(existing.payload or {}), **payload} if provider == "tcgapi" and status == "matched" else payload
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
    latest = session.scalar(select(PriceObservation).where(
        PriceObservation.card_id == card_id, PriceObservation.provider == provider,
        PriceObservation.provider_card_id == provider_card_id,
        PriceObservation.variant_id == variant_id,
    ).order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc()).limit(1))
    # A provider check (or a changed check date) is not a new market comp.
    if latest is not None and (
        latest.price, latest.currency, latest.condition, latest.printing,
        latest.grading_company, latest.grade,
    ) == (amount, currency[:3].upper(), condition, printing, grading_company, parsed_grade):
        return False
    if provider == "tcgapi":
        session.info.setdefault("catalog_price_cards", set()).add(card_id)
    session.add(PriceObservation(
        fingerprint=fingerprint, card_id=card_id, provider=provider,
        provider_card_id=provider_card_id, variant_id=variant_id,
        condition=condition, printing=printing, grading_company=grading_company,
        grade=parsed_grade, price=amount, currency=currency[:3].upper(),
        provider_updated_at=provider_updated_at, observed_at=datetime.now(UTC), payload=payload,
    ))
    pending_fingerprints.add(fingerprint)
    return True



def import_legacy_history(db, card, payload):
    from app.services.market_data_service import normalize_history
    now = datetime.now(UTC)
    points = normalize_history(payload, now.date())
    for point in points:
        db.merge(MarketHistory(card_id=card.id, fetched_at=now, **point))
    db.commit()
    return len(points)


def import_legacy_catalog_snapshot(db, game, payload, sets):
    if not isinstance(payload, dict) or len({str(row['id']) for row in sets}) != len(sets):
        logger.error('Invalid saved legacy catalog snapshot game=%s', game)
        raise ValueError('Invalid saved legacy catalog snapshot')
    db.merge(CatalogSnapshot(game=game, payload={'game': payload, 'sets': sets}, fetched_at=datetime.now(UTC)))
    db.commit()
    return len(sets)
