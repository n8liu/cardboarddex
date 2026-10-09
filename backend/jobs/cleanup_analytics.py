"""Run daily via the host scheduler, independent of paused ingestion workers."""
import logging
from app.database import SessionLocal
from app.services.site_analytics_service import cleanup

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        with SessionLocal() as db:
            deleted = cleanup(db)
        logger.info("Analytics retention removed %d expired records", deleted)
    except Exception as exc:
        logger.exception("Analytics retention failed: %s: %s", type(exc).__name__, exc)
        raise


if __name__ == "__main__":
    main()
