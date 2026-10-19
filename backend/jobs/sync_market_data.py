"""Retired history task compatibility. PPT ingestion stores history transactionally."""
import logging
from celery import shared_task
logger = logging.getLogger(__name__)


@shared_task(name='jobs.sync_market_data.sync_market_data')
def sync_market_data(*args, **kwargs):
    logger.warning('Retired history task acknowledged without provider access')
    return {'status': 'retired', 'replacement': 'jobs.sync_ppt.sync_ppt'}


if __name__ == '__main__':
    print(sync_market_data.run())
