from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "cardboarddex",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["jobs.refresh_live_stats", "jobs.refresh_trending", "jobs.refresh_movers", "jobs.sync_catalog", "jobs.collect_prices", "jobs.collect_ebay_prices", "jobs.cycle_prices", "jobs.sync_market_data", "jobs.check_listing_images", "jobs.sync_ppt", "jobs.ppt_report"],
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
    # The snapshot stays servable for 30 minutes; each build costs ~9s of database work.
    # Minutes 1,6,11,... avoid eBay (:15/:45) and the PPT report.
    "refresh-trending": {
        "task": "jobs.refresh_trending.refresh_trending",
        "schedule": crontab(minute="1-59/5"),
        "options": {"expires": 240, "time_limit": 110},
    },
    # Movers cannot rank on request within the API's 5s deadline. Minutes 3,8,13,...
    # avoid Trending (1,6,11,...) and eBay (:15/:45); a snapshot is served for a day.
    "refresh-movers": {
        "task": "jobs.refresh_movers.refresh_movers",
        "schedule": crontab(minute="3-59/5"),
        "options": {"expires": 240, "time_limit": 110},
    },
    # Minute :15 and :45 -> eBay market comps
    "collect-ebay-prices-alternating": {
        "task": "jobs.collect_ebay_prices.collect_ebay_prices",
        "schedule": crontab(minute="15,45"),
        "options": {"expires": 860, "time_limit": 840},
    },
}

if settings.listing_image_checks_enabled:
    celery_app.conf.beat_schedule["check-listing-images"] = {
        "task": "jobs.check_listing_images.check_listing_images",
        "schedule": 180.0,
        "options": {"expires": 120, "time_limit": 120},
    }


if settings.ppt_ingestion_enabled:
    celery_app.conf.beat_schedule["sync-pokemon-price-tracker"] = {
        "task": "jobs.sync_ppt.sync_ppt", "schedule": 15.0,
        "options": {"expires": 14, "time_limit": 180},
    }

if settings.ppt_ingestion_enabled:
    # No-op once the week's pool exists; sync_ppt falls back until then.
    celery_app.conf.beat_schedule["ppt-priority-pool"] = {
        "task": "jobs.sync_ppt.build_priority_pool", "schedule": 900.0,
        "options": {"expires": 840, "time_limit": 240},
    }

if settings.ppt_ingestion_enabled:
    # Diagnostics only; full-table counts are too costly to run every minute.
    celery_app.conf.beat_schedule["ppt-health-report"] = {
        "task": "jobs.ppt_report.publish_report", "schedule": crontab(minute="3,18,33,48"),
        "options": {"expires": 600, "time_limit": 20},
    }
