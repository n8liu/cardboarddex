"""Rebuild the movers, sealed and grading-profit snapshots that are due (every 12 hours).

Also runnable to seed after a release; pass --force to rebuild every snapshot now.
"""
import logging
import sys

from celery import shared_task

from app.services import grading_service, market_snapshots, movers_service, sealed_service

SNAPSHOTS = (movers_service, sealed_service, grading_service)


def refresh_due(*, force=False) -> dict[str, bool]:
    # One at a time, so the 192 MB worker holds a single snapshot in memory.
    return {service.SNAPSHOT_NAME: service.refresh_snapshot(force=force) for service in SNAPSHOTS}


@shared_task(name="jobs.refresh_market_snapshots.refresh_market_snapshots", time_limit=840)
def refresh_market_snapshots():
    return refresh_due()


def main(*, force=False) -> int:
    results = refresh_due(force=force)
    redis = market_snapshots.get_redis()
    if redis is None:
        return 1
    try:
        # False can mean either already fresh or failed. Verify every published part.
        ready = all(not market_snapshots.is_due(redis, service.SNAPSHOT_NAME,
                    getattr(service, "PARTS", ["all"])) for service in SNAPSHOTS)
        return 0 if ready and (not force or all(results.values())) else 1
    except Exception as exc:
        logging.getLogger(__name__).exception("Market snapshot verification failed error=%s: %s",
                                             type(exc).__name__, exc)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main(force="--force" in sys.argv))
