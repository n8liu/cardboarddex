from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "cardboarddex",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["jobs.sync_catalog", "jobs.collect_prices", "jobs.collect_ebay_prices", "jobs.cycle_prices"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    # Acknowledge tasks only after completion so a crashed worker doesn't silently drop work.
    task_acks_late=True,
    # Fetch one task at a time — prevents a slow job from blocking the queue behind it.
    worker_prefetch_multiplier=1,
)

celery_app.conf.beat_schedule = {
    # Alternating 15-minute schedule:
    # Minute :00 and :30 -> TCG API market prices
    "collect-tcgapi-prices-alternating": {
        "task": "jobs.collect_prices.collect_prices",
        "schedule": crontab(minute="0,30"),
        # Discard the task if still queued when the next window fires (860 s < 900 s).
        # Hard-kill the worker if a single run exceeds 14 minutes to prevent API quota bleed.
        "options": {"expires": 860, "time_limit": 840},
    },
    # Minute :15 and :45 -> eBay market comps
    "collect-ebay-prices-alternating": {
        "task": "jobs.collect_ebay_prices.collect_ebay_prices",
        "schedule": crontab(minute="15,45"),
        "options": {"expires": 860, "time_limit": 840},
    },
    "sync-catalog-daily": {
        "task": "jobs.sync_catalog.sync_catalog",
        "schedule": crontab(minute=0, hour=3),
        # Expire well before the next nightly run; allow up to ~58 minutes of runtime.
        "options": {"expires": 3540, "time_limit": 3480},
    },
}
