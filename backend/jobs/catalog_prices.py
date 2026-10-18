"""Backfill, verify or repair the derived catalog price projection (stored data only)."""
import argparse
import json
import logging
from datetime import UTC, datetime
from sqlalchemy import select, text
from app.database import SessionLocal
from app.models import CatalogPriceProjectionState as State
from app.services.catalog_prices import VERSION, backfill_batch, refresh_candidates, verify_projection

logger = logging.getLogger(__name__)


def run(action, *, restart=False, max_batches=None):
    if action == "backfill":
        batches, cards = 0, 0
        with SessionLocal() as db:
            while max_batches is None or batches < max_batches:
                count = backfill_batch(db, restart=restart and batches == 0)
                cards += count
                batches += 1
                state = db.get(State, VERSION)
                if state.complete:
                    break
            return {"batches": batches, "cards": cards, "complete": state.complete}
    with SessionLocal() as db:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            db.execute(text("SET LOCAL statement_timeout = '5000ms'"))
        result = verify_projection(db)
        state = db.get(State, VERSION)
        if action == "verify":
            if state and state.complete:
                state.verified_at = None if result["mismatched_cards"] else datetime.now(UTC)
                db.commit()
            result["ready"] = bool(state and state.complete and state.verified_at)
            return result
        # Repair in fresh READ COMMITTED transactions, not the old verification snapshot.
        db.rollback()
    for start in range(0, len(result["mismatched_cards"]), 250):
        with SessionLocal() as db:
            refresh_candidates(db, result["mismatched_cards"][start:start + 250])
            db.commit()
    return run("verify")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backfill", "verify", "repair"])
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args()
    if args.max_batches is not None and args.max_batches < 1:
        parser.error("--max-batches must be positive")
    logging.basicConfig(level=logging.INFO)
    try:
        result = run(args.action, restart=args.restart, max_batches=args.max_batches)
    except Exception as exc:
        logger.exception("Catalog projection %s failed error=%s: %s", args.action, type(exc).__name__, exc)
        raise
    print(json.dumps(result))
    return 1 if args.action != "backfill" and not result.get("ready") else 0


if __name__ == "__main__":
    raise SystemExit(main())
