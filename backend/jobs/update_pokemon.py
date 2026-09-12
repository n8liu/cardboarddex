"""Update All Cards for a Single Pokémon (TCG API + eBay Comps).

Usage:
    .venv/bin/python jobs/update_pokemon.py "Pikachu"
    .venv/bin/python jobs/update_pokemon.py "Charizard" --limit 20
    .venv/bin/python jobs/update_pokemon.py "Rayquaza" --tcg-only
    .venv/bin/python jobs/update_pokemon.py "Rayquaza" --ebay-only
    .venv/bin/python jobs/update_pokemon.py "Gengar" --delay 0.5
"""
import argparse
import logging
from pathlib import Path
import sys
import time
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.ebay import EbayClient, EbayConfigurationError
from app.models import Card
from app.providers import ProviderRequestLimitExceeded
from app.services.catalog_service import get_cards_for_pokemon
from app.tcgapi import TCGAPIClient, TCGAPIConfigurationError
from jobs.collect_ebay_prices import _collect_ebay_for_card
from jobs.collect_prices import run_price_collection

logger = logging.getLogger(__name__)


def update_cards_for_pokemon(
    session: Session,
    pokemon_name: str,
    limit: int | None = None,
    tcg_only: bool = False,
    ebay_only: bool = False,
    delay_seconds: float = 0.25,
    tcgapi_client: TCGAPIClient | None = None,
    ebay_client: EbayClient | None = None,
) -> dict[str, Any]:
    """
    Find all cards for a Pokémon character and update them across TCG API and eBay.
    """
    cards = get_cards_for_pokemon(session, pokemon_name, limit=limit)
    total_cards = len(cards)

    results: dict[str, Any] = {
        "pokemon": pokemon_name,
        "total_cards": total_cards,
        "tcgapi_observations": 0,
        "tcgapi_errors": 0,
        "ebay_raw_listings": 0,
        "ebay_observations": 0,
        "ebay_errors": 0,
    }

    if not cards:
        logger.warning("No cards found for Pokémon '%s'", pokemon_name)
        return results

    card_ids = [c.id for c in cards]

    # --- 1. TCG API Collection ---
    if not ebay_only:
        try:
            logger.info("Running TCG API price collection for %d cards...", total_cards)
            tcg_res = run_price_collection(
                session,
                card_ids=card_ids,
                tcgapi=tcgapi_client,
            )
            results["tcgapi_observations"] = tcg_res.get("tcgapi_observations", 0)
            results["tcgapi_errors"] = tcg_res.get("provider_errors", 0)
        except (
            ProviderRequestLimitExceeded,
            TCGAPIConfigurationError,
            SQLAlchemyError,
            httpx.HTTPError,
            Exception,
        ) as exc:
            results["tcgapi_errors"] += 1
            logger.exception("TCG API batch update failed for Pokémon '%s' error=%s: %s", pokemon_name, type(exc).__name__, exc)

    # --- 2. eBay Browse Comps Collection ---
    if not tcg_only:
        client = ebay_client or EbayClient()
        logger.info("Running eBay comp search for %d cards...", total_cards)
        for idx, card in enumerate(cards, start=1):
            set_title = card.set.name if card.set else "Unknown Set"
            try:
                raw_count, obs_count = _collect_ebay_for_card(session, card, client)
                results["ebay_raw_listings"] += raw_count
                results["ebay_observations"] += obs_count
                session.commit()
                print(
                    f"  [{idx}/{total_cards}] [{card.id}] {card.name} #{card.number} ({set_title}) "
                    f"-> {raw_count} raw listings, {obs_count} verified comp(s)"
                )
            except (
                httpx.HTTPError,
                KeyError,
                TypeError,
                ValueError,
                ProviderRequestLimitExceeded,
                EbayConfigurationError,
                SQLAlchemyError,
            ) as exc:
                session.rollback()
                session.info.pop("price_observation_fingerprints", None)
                results["ebay_errors"] += 1
                print(
                    f"  [{idx}/{total_cards}] [{card.id}] {card.name} #{card.number} ({set_title}) "
                    f"-> ERROR: {type(exc).__name__}: {exc}"
                )
                logger.exception(
                    "eBay collection failed for card_id=%s error=%s: %s",
                    card.id,
                    type(exc).__name__,
                    exc,
                )

            if delay_seconds > 0 and idx < total_cards:
                time.sleep(delay_seconds)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Update all cards for a specific Pokémon across both TCG API and eBay")
    parser.add_argument("pokemon", nargs="+", help="Pokémon character name (e.g. 'Pikachu', 'Charizard', 'Rayquaza')")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of cards to update")
    parser.add_argument("--tcg-only", action="store_true", help="Only update TCG API pricing")
    parser.add_argument("--ebay-only", action="store_true", help="Only update eBay comps")
    parser.add_argument("--delay", type=float, default=0.25, help="Seconds to pause between eBay requests (default: 0.25s)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    pokemon_query = " ".join(args.pokemon).strip()
    print(f"\n=======================================================")
    print(f"  Updating All Cards for Pokémon: {pokemon_query}")
    if args.limit:
        print(f"  (Limit: {args.limit} cards)")
    print(f"=======================================================\n")

    with SessionLocal() as session:
        cards = get_cards_for_pokemon(session, pokemon_query, limit=args.limit)
        if not cards:
            print(f"No cards found matching Pokémon character '{pokemon_query}' in database.")
            return

        print(f"Found {len(cards)} card(s) matching '{pokemon_query}'.")

        res = update_cards_for_pokemon(
            session=session,
            pokemon_name=pokemon_query,
            limit=args.limit,
            tcg_only=args.tcg_only,
            ebay_only=args.ebay_only,
            delay_seconds=args.delay,
        )

        print(f"\n=======================================================")
        print(f"  Summary for Pokémon: {pokemon_query}")
        print(f"  • Total cards processed: {res['total_cards']}")
        if not args.ebay_only:
            print(f"  • TCG API: {res['tcgapi_observations']} observation(s) added (errors: {res['tcgapi_errors']})")
        if not args.tcg_only:
            print(
                f"  • eBay:    {res['ebay_raw_listings']} listings searched, "
                f"{res['ebay_observations']} comps verified (errors: {res['ebay_errors']})"
            )
        print(f"=======================================================\n")
        print("Done!\n")


if __name__ == "__main__":
    main()
