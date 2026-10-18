"""Refresh stored-only global totals; also runnable to seed before frontend rollout."""
from celery import shared_task
from app.services.live_stats import refresh_snapshot


@shared_task(name="jobs.refresh_live_stats.refresh_live_stats", time_limit=20)
def refresh_live_stats():
    return refresh_snapshot()


if __name__ == "__main__":
    raise SystemExit(0 if refresh_snapshot() else 1)
