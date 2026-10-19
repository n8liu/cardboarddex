"""Retired task/import compatibility; this module never contacts a provider."""
import logging
from celery import shared_task
from app.database import SessionLocal  # Deprecated test/dependency compatibility.
from app.services.legacy_records import _state, _observation, select_exact_candidates, normalize_number, normalize_text
from app.services.card_lookup import find_cards_by_query as _find_cards_by_query
logger = logging.getLogger(__name__)


def run_price_collection(*args, **kwargs):
    logger.warning('Retired legacy collection requested; use app.services.ppt_refresh')
    return {'status': 'disabled'}


@shared_task(name='jobs.collect_prices.collect_prices')
def collect_prices():
    logger.warning('Retired price task acknowledged without provider access')
    return {'status': 'retired', 'replacement': 'jobs.sync_ppt.sync_ppt'}


if __name__ == '__main__':
    print(collect_prices.run())
