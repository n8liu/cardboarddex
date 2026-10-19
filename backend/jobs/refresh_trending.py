"""Publish the default Trending dashboard; also runnable to seed after a release."""
from celery import shared_task
from app.services.trending_service import refresh_snapshot


@shared_task(name="jobs.refresh_trending.refresh_trending", time_limit=110)
def refresh_trending():
    return refresh_snapshot()


if __name__ == "__main__":
    raise SystemExit(0 if refresh_snapshot() else 1)
