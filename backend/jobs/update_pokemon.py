"""Use the shared bounded refresh command for Pokémon queries."""
import logging
from app.services.catalog_service import get_cards_for_pokemon
from app.services.ppt_refresh import refresh_cards
from jobs.collect_ebay_prices import run_ebay_price_collection


def update_cards_for_pokemon(session, pokemon_name, limit=8, ppt_only=False, ebay_only=False, **legacy):
    if legacy.get('tcg_only'):
        logging.getLogger(__name__).warning('tcg_only is deprecated; using ppt_only')
        ppt_only = True
    cards = get_cards_for_pokemon(session, pokemon_name, limit=limit or 8)
    ids = [c.id for c in cards]
    result = {'total_cards': len(ids)}
    if ids and not ebay_only:
        result['ppt'] = refresh_cards(session, ids, limit=limit or 8)
    if ids and not ppt_only:
        result['ebay'] = run_ebay_price_collection(session, card_ids=ids, limit=limit or 8)
    return result


if __name__ == '__main__':
    from jobs.update_card import main
    main()
