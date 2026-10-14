"""Operator-only coverage and quota report: python -m jobs.passive_refresh_report."""
import json
import logging
from app.services.passive_refresh import coverage_report

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        print(json.dumps(coverage_report(), indent=2, sort_keys=True))
    except Exception:
        logging.exception('Passive refresh report failed')
        raise SystemExit(1)
