"""Publish every Market Movers ranking; also runnable to seed after a release."""
from celery import shared_task
from app.services.movers_service import refresh_snapshot


@shared_task(name="jobs.refresh_movers.refresh_movers", time_limit=110)
def refresh_movers():
    return refresh_snapshot()


if __name__ == "__main__":
    raise SystemExit(0 if refresh_snapshot() else 1)
