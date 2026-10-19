"""Bounded manual PPT + direct eBay refresh by canonical card ID or name."""
import argparse
import logging
from app.database import SessionLocal
from app.services.card_lookup import find_cards_by_query
from app.services.ppt_refresh import refresh_cards
from jobs.collect_ebay_prices import run_ebay_price_collection


def main():
    parser = argparse.ArgumentParser(description='Refresh PPT market prices and direct eBay comparisons')
    parser.add_argument('query', nargs='*')
    parser.add_argument('--card-id')
    parser.add_argument('--pokemon')
    parser.add_argument('--limit', type=int, default=8)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--ppt-only', '--tcg-only', dest='ppt_only', action='store_true')
    group.add_argument('--ebay-only', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    import sys
    if '--tcg-only' in sys.argv:
        logging.warning('--tcg-only is deprecated; using --ppt-only')
    if not 1 <= args.limit <= 50:
        parser.error('--limit must be 1–50')
    query = args.card_id or args.pokemon or ' '.join(args.query)
    if not query:
        parser.error('Specify --card-id, --pokemon or a card query')
    with SessionLocal() as db:
        cards = find_cards_by_query(db, query, args.limit)
        ids = [c.id for c in cards]
        if not ids:
            print({'status': 'no_matches'})
            return
        if not args.ebay_only:
            print({'ppt': refresh_cards(db, ids, limit=args.limit)})
        if not args.ppt_only:
            print({'ebay': run_ebay_price_collection(db, card_ids=ids, limit=args.limit)})


if __name__ == '__main__':
    main()
