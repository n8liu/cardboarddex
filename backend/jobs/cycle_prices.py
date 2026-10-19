"""Compatibility cycle entrypoint. Beat owns scheduling; no alternate daemon."""
import logging
from celery import shared_task
from app.services.ppt_refresh import refresh_cards
from jobs.collect_ebay_prices import run_ebay_price_collection


def run_price_cycle(session, card_id=None, card_ids=None, pokemon=None, ppt_limit=8, ebay_limit=8, **legacy):
    if 'tcg_limit' in legacy:
        logging.getLogger(__name__).warning('tcg_limit is deprecated; using ppt_limit')
        ppt_limit = legacy['tcg_limit']
    ids = card_ids or ([card_id] if card_id else None)
    if pokemon:
        from app.services.catalog_service import get_cards_for_pokemon
        ids = [c.id for c in get_cards_for_pokemon(session, pokemon, limit=50)]
    result = {}
    if ppt_limit != 0:
        result['ppt'] = refresh_cards(session, ids, limit=ppt_limit or 8)
    if ebay_limit != 0:
        result['ebay'] = run_ebay_price_collection(session, card_ids=ids, limit=ebay_limit or 8)
    return result


@shared_task(name='jobs.cycle_prices.cycle_prices')
def cycle_prices():
    logging.getLogger(__name__).warning('Retired cycle task acknowledged; PPT and eBay have dedicated schedules')
    return {'status': 'retired'}


if __name__ == '__main__':
    from jobs.update_card import main
    main()
