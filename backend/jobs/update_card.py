"""Unified Single Card Updater (TCG API + eBay Comps).

Usage:
    .venv/bin/python jobs/update_card.py --card-id 28402
    .venv/bin/python jobs/update_card.py 28402
    .venv/bin/python jobs/update_card.py "Rayquaza Legends Awakened"
"""
import argparse
import logging
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import SessionLocal
from app.models import Card
from jobs.collect_prices import _find_cards_by_query
from jobs.cycle_prices import run_price_cycle

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Update a single Pokémon card across both TCG API and eBay")
    parser.add_argument("query", nargs="*", help="Card ID or name query (e.g. '28402' or 'Rayquaza 14')")
    parser.add_argument("--card-id", type=str, help="Target specific canonical card ID")
    parser.add_argument("--pokemon", type=str, help="Target all cards for a specific Pokémon (e.g. 'Pikachu')")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of cards to update (when using --pokemon)")
    parser.add_argument("--delay", type=float, default=0.25, help="Delay between eBay requests in seconds (when using --pokemon)")
    parser.add_argument("--tcg-only", action="store_true", help="Only update TCG API pricing")
    parser.add_argument("--ebay-only", action="store_true", help="Only update eBay comps")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.pokemon:
        from app.services.catalog_service import get_cards_for_pokemon
        from jobs.update_pokemon import update_cards_for_pokemon

        with SessionLocal() as session:
            cards = get_cards_for_pokemon(session, args.pokemon, limit=args.limit)
            if not cards:
                print(f"No cards found matching Pokémon character '{args.pokemon}' in database.")
                return
            print(f"\nFound {len(cards)} card(s) matching '{args.pokemon}'.")
            res = update_cards_for_pokemon(
                session=session,
                pokemon_name=args.pokemon,
                limit=args.limit,
                tcg_only=args.tcg_only,
                ebay_only=args.ebay_only,
                delay_seconds=args.delay,
            )
            print(f"\nSummary for Pokémon: {args.pokemon}")
            print(f"  • Total cards processed: {res['total_cards']}")
            if not args.ebay_only:
                print(f"  • TCG API: {res['tcgapi_observations']} observation(s) added (errors: {res['tcgapi_errors']})")
            if not args.tcg_only:
                print(
                    f"  • eBay:    {res['ebay_raw_listings']} listings searched, "
                    f"{res['ebay_observations']} comps verified (errors: {res['ebay_errors']})"
                )
            print("Done!\n")
            return

    with SessionLocal() as session:
        target_id = args.card_id
        target_card = None
        if not target_id and args.query:
            query_str = " ".join(args.query).strip()
            matching = _find_cards_by_query(session, query_str, limit=5)
            if not matching:
                print(f"No cards found matching query: '{query_str}'")
                return
            if len(matching) > 1:
                print(f"Found {len(matching)} matching cards for '{query_str}':")
                for c in matching:
                    print(f"  - [{c.id}] {c.name} #{c.number} ({c.set.name if c.set else ''})")
                print(f"\nUpdating first match: [{matching[0].id}] {matching[0].name} #{matching[0].number}...")
            target_card = matching[0]
            target_id = target_card.id
        elif target_id:
            target_card = session.get(Card, target_id)
            if not target_card:
                print(f"Card ID '{target_id}' not found in database.")
                return
        else:
            parser.print_help()
            return

        set_name = target_card.set.name if target_card.set else "Unknown Set"
        print(f"\n=======================================================")
        print(f"  Updating: [{target_card.id}] {target_card.name} #{target_card.number} ({set_name})")
        print(f"=======================================================\n")

        tcg_limit = 0 if args.ebay_only else 1
        ebay_limit = 0 if args.tcg_only else 1

        res = run_price_cycle(
            session,
            card_id=target_id,
            tcg_limit=tcg_limit,
            ebay_limit=ebay_limit,
        )

        tcg_res = res.get("tcgapi") or {}
        ebay_res = res.get("ebay") or {}

        print(f"\nSummary for [{target_card.id}] {target_card.name}:")
        if not args.ebay_only:
            tcg_obs = tcg_res.get("tcgapi_observations", 0) if isinstance(tcg_res, dict) else 0
            tcg_err = tcg_res.get("provider_errors", 0) if isinstance(tcg_res, dict) else 0
            print(f"  • TCG API: {tcg_obs} observation(s) added (errors: {tcg_err})")
        if not args.tcg_only:
            ebay_raw = ebay_res.get("raw_listings", 0) if isinstance(ebay_res, dict) else 0
            ebay_obs = ebay_res.get("ebay_observations", 0) if isinstance(ebay_res, dict) else 0
            ebay_err = ebay_res.get("provider_errors", 0) if isinstance(ebay_res, dict) else 0
            print(f"  • eBay:    {ebay_raw} listings searched, {ebay_obs} comps verified (errors: {ebay_err})")
        print("Done!\n")


if __name__ == "__main__":
    main()
