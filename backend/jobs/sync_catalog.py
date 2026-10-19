"""Retired catalog task compatibility. PPT discovery owns catalog refresh."""
import logging
from celery import shared_task
logger = logging.getLogger(__name__)


def run_catalog_sync(*args, **kwargs):
    logger.warning('Legacy catalog sync is retired; use PPT discovery')
    return {'status': 'disabled'}


@shared_task(name='jobs.sync_catalog.sync_catalog')
def sync_catalog(*args, **kwargs):
    logger.warning('Retired catalog task acknowledged without provider access')
    return {'status': 'retired', 'replacement': 'jobs.sync_ppt.sync_ppt'}


if __name__ == '__main__':
    print(sync_catalog.run())
