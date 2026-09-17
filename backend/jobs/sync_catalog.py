import argparse
import hashlib
import json
import logging
from pathlib import Path
import re
import sys
from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

# Ensure backend root is in sys.path when executed as a direct script
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.formatters import (
    normalize_text,
    parse_iso_datetime as _parse_datetime,
    to_decimal as _decimal,
)
from app.common.redis import get_durable_redis as get_redis
from app.config import get_settings
from app.database import SessionLocal
from app.providers.limiter import ProviderRequestLimitExceeded
from app.models import Card, PriceObservation, ProviderCardState, Set
from app.tcgapi.client import (
    TCGAPIClient,
    local_card_id,
    parse_release_date,
    split_card_number,
)

logger = logging.getLogger(__name__)
BATCH_SIZE = 250


def _chunks(items: Iterable[dict[str, Any]]) -> Iterable[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for item in items:
        batch.append(item)
        if len(batch) == BATCH_SIZE:
            yield batch
            batch = []
    if batch:
        yield batch


def _latest_sets(payloads: Iterable[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    ordered = sorted(
        payloads,
        key=lambda item: parse_release_date(item.get("release_date")) or date.min,
        reverse=True,
    )
    if limit is not None and limit > 0:
        return ordered[:limit]
    return ordered


def _upsert_sets(session: Session, payloads: Iterable[dict[str, Any]]) -> int:
    count = 0
    for batch in _chunks(payloads):
        for item in batch:
            game_slug = str(item.get("game_slug") or "")
            game_name = str(item.get("game_name") or "")
            series = (
                "Pokemon Japan"
                if (game_slug == "pokemon-japan" or "japan" in game_name.lower())
                else (item.get("series") or "Pokemon")
            )
            session.merge(
                Set(
                    id=str(item["id"]),
                    name=item["name"],
                    series=series,
                    printed_total=item.get("card_count"),
                    release_date=parse_release_date(item.get("release_date")),
                    updated_at=datetime.now(UTC),
                )
            )
        session.commit()
        count += len(batch)
        logger.info("Catalog set batch committed batch_size=%s total=%s", len(batch), count)
    return count


def _upsert_cards(
    session: Session,
    payloads: Iterable[dict[str, Any]],
    set_totals: dict[str, int | None],
) -> tuple[int, int]:
    card_count = 0
    price_count = 0
    pending_fingerprints: set[str] = session.info.setdefault("price_observation_fingerprints", set())

    for batch in _chunks(payloads):
        candidate_observations: list[tuple[str, PriceObservation]] = []
        batch_card_states: dict[str, tuple[str, dict[str, Any]]] = {}

        for item in batch:
            source_id = str(item["id"])
            set_id = str(item["_set_id"])
            number, printed_total = split_card_number(
                item.get("number"), set_totals.get(set_id)
            )
            card = Card(
                id=local_card_id(source_id),
                name=item["name"],
                set_id=set_id,
                number=number,
                printed_total=printed_total,
                rarity=item.get("rarity"),
                image_url=item.get("image_url"),
                updated_at=datetime.now(UTC),
            )
            session.merge(card)
            batch_card_states[card.id] = (source_id, item)

            variants = item.get("variants") or []
            if not variants and (item.get("market_price") is not None or item.get("low_price") is not None):
                variants = [{
                    "printing": item.get("printing") or "Normal",
                    "market_price": item.get("market_price"),
                    "low_price": item.get("low_price"),
                    "median_price": item.get("median_price"),
                    "lowest_with_shipping": item.get("lowest_with_shipping"),
                    "buylist_price": item.get("buylist_price"),
                    "price_change_24h": item.get("price_change_24h"),
                    "price_change_7d": item.get("price_change_7d"),
                    "price_change_30d": item.get("price_change_30d"),
                    "total_listings": item.get("total_listings"),
                    "last_updated_at": item.get("price_updated_at") or item.get("last_updated_at"),
                }]
            if not isinstance(variants, list):
                continue
            for variant in variants:
                if not isinstance(variant, dict):
                    continue
                printing = variant.get("printing")
                market = _decimal(variant.get("market_price"))
                low = _decimal(variant.get("low_price"))
                median = _decimal(variant.get("median_price"))
                observed_price = market if market is not None else median
                if observed_price is None:
                    continue
                observed_at = _parse_datetime(variant.get("last_updated_at")) or datetime.now(UTC)
                fingerprint = hashlib.sha256(
                    f"{card.id}:{printing}:{observed_price}:{observed_at.isoformat()}".encode()
                ).hexdigest()
                if fingerprint in pending_fingerprints:
                    continue
                pending_fingerprints.add(fingerprint)
                # Build a flat payload so _extract_float() can read fields directly,
                # plus keep the raw sub-keys for backward compat and debugging.
                def _to_float_or_none(v: Any) -> float | None:
                    try:
                        return float(v) if v is not None else None
                    except (TypeError, ValueError):
                        return None

                flat_payload: dict[str, Any] = {
                    "market_price": _to_float_or_none(market),
                    "low_price": _to_float_or_none(low),
                    "median_price": _to_float_or_none(median),
                    "lowest_with_shipping": _to_float_or_none(variant.get("lowest_with_shipping")),
                    "buylist_price": _to_float_or_none(variant.get("buylist_price")),
                    "price_change_24h": variant.get("price_change_24h"),
                    "price_change_7d": variant.get("price_change_7d"),
                    "price_change_30d": variant.get("price_change_30d"),
                    "total_listings": variant.get("total_listings"),
                    # Kept for debugging / backward compat
                    "variant": variant,
                    "raw_card": item,
                }
                candidate_observations.append(
                    (
                        fingerprint,
                        PriceObservation(
                            fingerprint=fingerprint,
                            card_id=card.id,
                            provider="tcgapi",
                            provider_card_id=source_id,
                            variant_id=f"{source_id}:{normalize_text(printing) or 'standard'}",
                            price=observed_price,
                            currency="USD",
                            condition=None,
                            printing=printing,
                            observed_at=observed_at,
                            provider_updated_at=observed_at,
                            payload=flat_payload,
                        ),
                    )
                )

        if candidate_observations:
            fps = [fp for fp, _ in candidate_observations]
            existing_fps = set(
                session.scalars(
                    select(PriceObservation.fingerprint).where(
                        PriceObservation.fingerprint.in_(fps)
                    )
                ).all()
            )
            inserted = 0
            for fp, obs in candidate_observations:
                if fp not in existing_fps:
                    session.add(obs)
                    existing_fps.add(fp)
                    inserted += 1
            price_count += inserted

        if batch_card_states:
            card_ids = list(batch_card_states.keys())
            existing_states = {
                st.card_id: st
                for st in session.scalars(
                    select(ProviderCardState).where(
                        ProviderCardState.card_id.in_(card_ids),
                        ProviderCardState.provider == "tcgapi",
                    )
                ).all()
            }
            for c_id, (s_id, c_item) in batch_card_states.items():
                st = existing_states.get(c_id)
                if st is None:
                    st = ProviderCardState(
                        card_id=c_id,
                        provider="tcgapi",
                        provider_card_id=s_id,
                        match_status="matched",
                        match_method="canonical_tcgapi_id",
                        payload={"card": c_item},
                        last_synced_at=datetime.now(UTC),
                    )
                    session.add(st)
                    existing_states[c_id] = st
                else:
                    st.provider_card_id = s_id
                    st.match_status = "matched"
                    st.match_method = "canonical_tcgapi_id"
                    st.payload = {"card": c_item}
                    st.last_synced_at = datetime.now(UTC)

        session.commit()
        card_count += len(batch)
        logger.info("Catalog card batch committed batch_size=%s total_cards=%s total_prices=%s",
                    len(batch), card_count, price_count)

    return card_count, price_count


CURSOR_KEY_PREFIX = "cardboarddex:sync:cursor"


def get_sync_cursor(game: str, redis_client: Any = None) -> dict[str, Any] | None:
    """Retrieve the sync cursor checkpoint for a given game, if any."""
    r = redis_client or get_redis()
    if r is None:
        return None
    try:
        raw = r.get(f"{CURSOR_KEY_PREFIX}:{game}")
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning(
            "Failed to read catalog sync cursor game=%s error=%s: %s",
            game, type(exc).__name__, exc,
        )
        return None


def set_sync_cursor(game: str, last_set_id: str, set_index: int, redis_client: Any = None) -> None:
    """Save the sync cursor checkpoint in Redis to enable resumption."""
    r = redis_client or get_redis()
    if r is None:
        return
    try:
        payload = json.dumps({
            "last_synced_set_id": last_set_id,
            "set_index": set_index,
            "updated_at": datetime.now(UTC).isoformat(),
        })
        r.set(f"{CURSOR_KEY_PREFIX}:{game}", payload, ex=86400 * 3)
    except Exception as exc:
        logger.warning(
            "Failed to write catalog sync cursor game=%s error=%s: %s",
            game, type(exc).__name__, exc,
        )


def clear_sync_cursor(game: str, redis_client: Any = None) -> None:
    """Clear the sync cursor checkpoint for a given game."""
    r = redis_client or get_redis()
    if r is None:
        return
    try:
        r.delete(f"{CURSOR_KEY_PREFIX}:{game}")
    except Exception as exc:
        logger.warning(
            "Failed to clear catalog sync cursor game=%s error=%s: %s",
            game, type(exc).__name__, exc,
        )


def run_catalog_sync(
    session: Session,
    client: TCGAPIClient | None = None,
    set_limit: int | None = None,
    game: str = "pokemon",
    resume: bool = False,
    redis_client: Any = None,
) -> dict[str, int]:
    tcgapi_client = client or TCGAPIClient()
    configured_limit = set_limit if set_limit is not None else get_settings().tcgapi_sync_set_limit
    set_count = 0
    card_count = 0
    price_count = 0
    try:
        games = ["pokemon", "pokemon-japan"] if game == "all" else [game]
        for g in games:
            try:
                raw_sets = tcgapi_client.iter_sets(game=g)
            except TypeError:
                raw_sets = tcgapi_client.iter_sets()
            sets = _latest_sets(raw_sets, configured_limit)

            if resume:
                cursor = get_sync_cursor(g, redis_client=redis_client)
                if cursor and "last_synced_set_id" in cursor:
                    last_id = cursor["last_synced_set_id"]
                    idx_match = next((i for i, s in enumerate(sets) if str(s.get("id")) == str(last_id)), None)
                    if idx_match is not None and idx_match + 1 < len(sets):
                        logger.info(
                            "Resuming catalog sync game=%s from set_index=%s after set_id=%s",
                            g, idx_match + 1, last_id,
                        )
                        sets = sets[idx_match + 1:]
                    elif idx_match is not None and idx_match + 1 >= len(sets):
                        logger.info("Catalog sync cursor for game=%s indicates all sets completed", g)
                        clear_sync_cursor(g, redis_client=redis_client)
                        continue

            if not sets:
                continue

            cur_set_count = _upsert_sets(session, sets)
            set_count += cur_set_count
            set_ids = [str(item["id"]) for item in sets]
            set_totals = {str(item["id"]): item.get("card_count") for item in sets}

            try:
                c_cnt, p_cnt = _upsert_cards(
                    session,
                    tcgapi_client.iter_cards(set_ids),
                    set_totals,
                )
                card_count += c_cnt
                price_count += p_cnt
                clear_sync_cursor(g, redis_client=redis_client)
            except ProviderRequestLimitExceeded as quota_exc:
                logger.warning(
                    "TCG API daily quota limit reached during catalog sync game=%s completed_sets=%s: %s",
                    g, set_count, quota_exc,
                )
                if set_ids:
                    set_sync_cursor(g, set_ids[-1], len(sets) - 1, redis_client=redis_client)
                break
    except (KeyError, TypeError, ValueError, SQLAlchemyError) as exc:
        session.rollback()
        logger.exception(
            "Catalog sync failed sets_completed=%s error=%s: %s",
            set_count, type(exc).__name__, exc,
        )
        raise
    logger.info("Catalog sync complete sets=%s cards=%s prices=%s", set_count, card_count, price_count)
    return {"sets": set_count, "cards": card_count, "prices": price_count}


@shared_task(name="jobs.sync_catalog.sync_catalog", autoretry_for=(), max_retries=0)
def sync_catalog(game: str = "all", resume: bool = True) -> dict[str, int]:
    with SessionLocal() as session:
        return run_catalog_sync(session, game=game, resume=resume)


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize Pokémon catalog and prices from TCG API")
    parser.add_argument("--all", action="store_true", help="Synchronize all sets in the catalog")
    parser.add_argument("--limit", "--sets", type=int, default=None, help="Maximum number of sets to synchronize")
    parser.add_argument("--game", choices=["pokemon", "pokemon-japan", "all"], default="all", help="Game to sync (pokemon, pokemon-japan, or all)")
    parser.add_argument("--resume", action="store_true", help="Resume from last stored sync cursor checkpoint")
    parser.add_argument("--reset-cursor", action="store_true", help="Reset and clear any existing sync cursor")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.reset_cursor:
        games = ["pokemon", "pokemon-japan"] if args.game == "all" else [args.game]
        for g in games:
            clear_sync_cursor(g)
        logger.info("Sync cursor(s) cleared for game=%s", args.game)

    limit = None if args.all else args.limit
    with SessionLocal() as session:
        result = run_catalog_sync(session, set_limit=limit, game=args.game, resume=args.resume)
        logger.info("Manual catalog sync finished result=%s", result)
        print(result)


if __name__ == "__main__":
    main()
