import argparse
import logging
from pathlib import Path
import sys
import time
from datetime import UTC, datetime
from typing import Any

# Ensure backend root is in sys.path when executed as a direct script
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from celery import shared_task
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.ebay import EbayClient, EbayConfigurationError
from app.providers import ProviderRequestLimitExceeded
from app.services.catalog_service import get_cards_for_pokemon
from app.tcgapi import TCGAPIClient, TCGAPIConfigurationError
from jobs.collect_ebay_prices import run_ebay_price_collection
from jobs.collect_prices import run_price_collection

logger = logging.getLogger(__name__)


def run_price_cycle(
    session: Session,
    card_id: str | None = None,
    card_ids: list[str] | None = None,
    pokemon: str | None = None,
    tcg_limit: int | None = None,
    ebay_limit: int | None = None,
    tcgapi_client: TCGAPIClient | None = None,
    ebay_client: EbayClient | None = None,
) -> dict[str, Any]:
    """
    Run an automated price cycle across TCG API and eBay.
    If pokemon is provided, updates all cards for that Pokémon character.
    If card_ids or card_id is provided, updates those specific cards.
    Otherwise selects least-recently-synced cards to ensure continuous round-robin price refreshing.
    """
    cycle_start = datetime.now(UTC)
    target_ids: list[str] | None = None
    if pokemon:
        matched_cards = get_cards_for_pokemon(session, pokemon)
        target_ids = [c.id for c in matched_cards]
    elif card_ids:
        target_ids = list(card_ids)
    elif card_id:
        target_ids = [card_id]

    results: dict[str, Any] = {
        "started_at": cycle_start.isoformat(),
        "card_id": card_id,
        "card_ids": target_ids,
        "pokemon": pokemon,
        "tcgapi": None,
        "ebay": None,
        "status": "completed",
    }

    effective_tcg_limit = (
        len(target_ids) if (target_ids is not None and tcg_limit is None)
        else (tcg_limit if tcg_limit is not None else (1 if card_id else None))
    )
    effective_ebay_limit = (
        len(target_ids) if (target_ids is not None and ebay_limit is None)
        else (ebay_limit if ebay_limit is not None else (1 if card_id else None))
    )

    # 1. Cycle TCG API pricing
    if target_ids is not None or tcg_limit is None or tcg_limit > 0:
        try:
            logger.info("Starting TCG API pricing cycle limit=%s card_ids=%s", effective_tcg_limit, target_ids)
            tcg_res = run_price_collection(
                session,
                limit=effective_tcg_limit,
                card_id=card_id if not target_ids or len(target_ids) == 1 else None,
                card_ids=target_ids,
                tcgapi=tcgapi_client,
            )
            results["tcgapi"] = tcg_res
        except (
            ProviderRequestLimitExceeded,
            TCGAPIConfigurationError,
            SQLAlchemyError,
            Exception,
        ) as exc:
            results["tcgapi"] = {"error": f"{type(exc).__name__}: {exc}"}
            logger.exception(
                "TCG API price cycle failed error=%s: %s",
                type(exc).__name__,
                exc,
            )

    # 2. Cycle eBay pricing
    if target_ids is not None or ebay_limit is None or ebay_limit > 0:
        try:
            logger.info("Starting eBay pricing cycle limit=%s card_ids=%s", effective_ebay_limit, target_ids)
            ebay_res = run_ebay_price_collection(
                session,
                limit=effective_ebay_limit,
                card_id=card_id if not target_ids or len(target_ids) == 1 else None,
                card_ids=target_ids,
                ebay_client=ebay_client,
            )
            results["ebay"] = ebay_res
        except (
            ProviderRequestLimitExceeded,
            EbayConfigurationError,
            SQLAlchemyError,
            Exception,
        ) as exc:
            results["ebay"] = {"error": f"{type(exc).__name__}: {exc}"}
            logger.exception(
                "eBay price cycle failed error=%s: %s",
                type(exc).__name__,
                exc,
            )

    results["completed_at"] = datetime.now(UTC).isoformat()
    logger.info("Completed price cycle summary=%s", results)
    return results


@shared_task(name="jobs.cycle_prices.cycle_prices", autoretry_for=(), max_retries=0)
def cycle_prices() -> dict[str, Any]:
    """Celery task for scheduled automated price cycling."""
    with SessionLocal() as session:
        return run_price_cycle(session, tcg_limit=15, ebay_limit=5)


def run_continuous_daemon(
    interval_seconds: int = 900,
    tcg_limit: int = 15,
    ebay_limit: int = 5,
    alternate: bool = True,
) -> None:
    """Run continuous price cycling in a loop with sleep intervals."""
    mode_desc = "alternating (TCG API -> eBay -> TCG API...)" if alternate else "combined (both per cycle)"
    logger.info(
        "Starting continuous price cycling daemon interval=%ss mode=%s tcg_limit=%s ebay_limit=%s",
        interval_seconds,
        mode_desc,
        tcg_limit,
        ebay_limit,
    )
    cycle_num = 1
    while True:
        logger.info("--- Starting Price Cycle #%s ---", cycle_num)
        try:
            with SessionLocal() as session:
                if alternate:
                    # Odd cycles: TCG API; Even cycles: eBay
                    if cycle_num % 2 == 1:
                        logger.info("Cycle #%s [TCG API Phase] updating up to %s cards...", cycle_num, tcg_limit)
                        run_price_cycle(session, tcg_limit=tcg_limit, ebay_limit=0)
                    else:
                        logger.info("Cycle #%s [eBay Comps Phase] updating up to %s cards...", cycle_num, ebay_limit)
                        run_price_cycle(session, tcg_limit=0, ebay_limit=ebay_limit)
                else:
                    run_price_cycle(session, tcg_limit=tcg_limit, ebay_limit=ebay_limit)
        except Exception as exc:
            logger.exception("Continuous cycle error=%s: %s", type(exc).__name__, exc)
        cycle_num += 1
        logger.info(
            "Cycle complete. Sleeping %ss (%.1f mins) before next cycle...",
            interval_seconds,
            interval_seconds / 60,
        )
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Automated price cycling for TCG API and eBay")
    parser.add_argument("query", nargs="*", help="Optional card ID or search query to update directly")
    parser.add_argument("--card-id", type=str, help="Target a specific canonical card ID across both TCG API and eBay")
    parser.add_argument("--pokemon", type=str, help="Target all cards for a specific Pokémon (e.g. 'Pikachu')")
    parser.add_argument("--tcg-limit", type=int, default=15, help="Number of cards to update via TCG API")
    parser.add_argument("--ebay-limit", type=int, default=5, help="Number of cards to update via eBay")
    parser.add_argument("--continuous", action="store_true", help="Run continuously in a loop")
    parser.add_argument("--interval", type=int, default=900, help="Interval in seconds between continuous cycles (default: 900 = 15 min)")
    parser.add_argument("--alternate", action="store_true", default=True, help="Alternate between TCG API and eBay every interval (default: True)")
    parser.add_argument("--no-alternate", dest="alternate", action="store_false", help="Run both TCG API and eBay simultaneously every interval")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.continuous:
        run_continuous_daemon(
            interval_seconds=args.interval,
            tcg_limit=args.tcg_limit,
            ebay_limit=args.ebay_limit,
            alternate=args.alternate,
        )
    else:
        with SessionLocal() as session:
            target_id = args.card_id
            if not target_id and args.query:
                from jobs.collect_prices import _find_cards_by_query
                query_str = " ".join(args.query).strip()
                matching = _find_cards_by_query(session, query_str, limit=5)
                if not matching:
                    print(f"No cards found matching query: '{query_str}'")
                    return
                print(f"Found {len(matching)} matching card(s) for '{query_str}':")
                for c in matching:
                    print(f"\n--- Updating [{c.id}] {c.name} #{c.number} ({c.set.name if c.set else ''}) ---")
                    res = run_price_cycle(session, card_id=c.id)
                    print("Cycle result:", res)
                return

            res = run_price_cycle(
                session,
                card_id=target_id,
                pokemon=args.pokemon,
                tcg_limit=args.tcg_limit,
                ebay_limit=args.ebay_limit,
            )
            print("Cycle result:", res)


if __name__ == "__main__":
    main()
