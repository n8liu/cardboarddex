from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "cardboarddex",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["jobs.refresh_live_stats", "jobs.sync_catalog", "jobs.collect_prices", "jobs.collect_ebay_prices", "jobs.cycle_prices", "jobs.sync_market_data", "jobs.check_listing_images", "jobs.sync_ppt"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    result_expires=3600,
    broker_connection_timeout=2,
    broker_transport_options={"socket_timeout": 2, "socket_connect_timeout": 2},
    redis_socket_timeout=2,
    redis_socket_connect_timeout=2,
    # Acknowledge tasks only after completion so a crashed worker doesn't silently drop work.
    task_acks_late=True,
    # Fetch one task at a time — prevents a slow job from blocking the queue behind it.
    worker_prefetch_multiplier=1,
)

celery_app.conf.beat_schedule = {
    "refresh-live-stats": {
        "task": "jobs.refresh_live_stats.refresh_live_stats",
        "schedule": 60.0,
        "options": {"expires": 55, "time_limit": 20},
    },
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
        "kwargs": {"game": "all"},
        # Expire well before the next nightly run; allow up to ~58 minutes of runtime.
        "options": {"expires": 3540, "time_limit": 3480},
    },
}

# Opt-in only: keep history collection off while production ingestion is paused.
if settings.market_history_enabled:
    celery_app.conf.beat_schedule["sync-market-history"] = {
        "task": "jobs.sync_market_data.sync_market_data",
        "schedule": crontab(minute=10),
        "kwargs": {"limit": 5},
        "options": {"expires": 1800, "time_limit": 600},
    }
    celery_app.conf.beat_schedule["discover-market-catalog"] = {
        "task": "jobs.sync_market_data.sync_market_data",
        "schedule": crontab(minute=40, hour=4),
        "kwargs": {"limit": 1, "discover": True},
        "options": {"expires": 1800, "time_limit": 600},
    }


if settings.listing_image_checks_enabled:
    celery_app.conf.beat_schedule["check-listing-images"] = {
        "task": "jobs.check_listing_images.check_listing_images",
        "schedule": 180.0,
        "options": {"expires": 120, "time_limit": 120},
    }


if not settings.tcgapi_ingestion_enabled:
    for name in ("collect-tcgapi-prices-alternating", "sync-catalog-daily", "sync-market-history", "discover-market-catalog"):
        celery_app.conf.beat_schedule.pop(name, None)

if settings.ppt_ingestion_enabled:
    celery_app.conf.beat_schedule["sync-pokemon-price-tracker"] = {
        "task": "jobs.sync_ppt.sync_ppt", "schedule": 15.0,
        "options": {"expires": 14, "time_limit": 180},
    }
