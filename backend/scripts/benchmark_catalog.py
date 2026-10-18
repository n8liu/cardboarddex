"""Uncached catalog benchmark. Use an explicitly supplied disposable/restored database.

Read benchmarks do not modify source data or change PostgreSQL caches. Optional
ingestion probes roll back synthetic writes (but consume sequence values). EXPLAIN ANALYZE executes
queries, bounded by a five-second statement timeout. Never prints the database URL.
"""
import argparse
import hashlib
import uuid
import json
import logging
import math
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Response
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session
from app.config import get_settings
from app.models import Card, PriceObservation
from app.routers.catalog import search_cards
from app.services.catalog_service import query_pokemon_cards, get_set_statistics
from app.services.catalog_prices import require_ready, refresh_candidates

logger = logging.getLogger(__name__)


def percentile(values, fraction):
    return sorted(values)[min(len(values)-1, max(0, math.ceil(len(values)*fraction)-1))]


def benchmark(url, *, projection, repetitions=7, explain=False, measure_ingestion=False):
    engine = create_engine(url)
    settings = get_settings()
    original = settings.catalog_current_prices_enabled, settings.ppt_primary_enabled
    settings.catalog_current_prices_enabled = projection
    trace = []
    @event.listens_for(engine, "before_cursor_execute")
    def before(conn, cursor, sql, params, context, many):
        context._catalog_started = time.perf_counter()
    @event.listens_for(engine, "after_cursor_execute")
    def after(conn, cursor, sql, params, context, many):
        if sql.lstrip().upper().startswith(("SELECT", "WITH")):
            trace.append((sql, params, (time.perf_counter()-context._catalog_started)*1000))
    try:
        with Session(engine) as db:
            if projection: require_ready(db)
            set_id = db.scalar(select(Card.set_id).group_by(Card.set_id).order_by(func.count().desc()).limit(1))
            counts = {"cards": db.scalar(select(func.count()).select_from(Card)),
                      "observations": db.scalar(select(func.count()).select_from(PriceObservation))}
            version = db.scalar(text("SELECT version()"))
        def search(db, **extra):
            options = dict(q="", sort_by="price_desc", limit=60, offset=0, set_id=None, game="pokemon",
                           hide_sealed=True, sealed_only=False, min_price=None, max_price=None)
            return search_cards.__wrapped__(Response(), db=db, **(options | extra))
        cases = {
            "broad_price_desc": lambda db: search(db),
            "broad_price_asc": lambda db: search(db, sort_by="price_asc"),
            "broad_price_range": lambda db: search(db, min_price=10, max_price=100),
            "search": lambda db: search(db, q="Pikachu"),
            "set": lambda db: search(db, set_id=set_id),
            "name": lambda db: search(db, sort_by="name"),
            "deep_page": lambda db: search(db, offset=1000),
            "japanese": lambda db: search(db, game="pokemon-japan"),
            "pokemon": lambda db: query_pokemon_cards(db, "Pikachu"),
            "set_stats": lambda db: get_set_statistics(db, set_id, use_cache=False),
        }
        results = {}
        for primary in (False, True):
            settings.ppt_primary_enabled = primary
            for name, call in cases.items():
                metrics, plans, queries = [], [], []
                for iteration in range(repetitions):
                    with Session(engine) as db:
                        started = time.perf_counter()
                        db.connection()
                        acquisition = (time.perf_counter()-started)*1000
                        db.execute(text("SET LOCAL statement_timeout = '5000ms'"))
                        trace.clear()
                        started = time.perf_counter()
                        result = call(db)
                        handler = (time.perf_counter()-started)*1000
                        queries = list(trace)
                        started = time.perf_counter()
                        if isinstance(result, list):
                            serialized = [row.model_dump(mode="json") for row in result]
                        else:
                            serialized = result.model_dump(mode="json")
                        json.dumps(serialized)
                        serialization = (time.perf_counter()-started)*1000
                        metrics.append({"connection_ms": acquisition, "sql_ms": sum(row[2] for row in queries),
                                        "handler_ms": handler, "serialization_ms": serialization})
                if explain:
                    with engine.connect() as conn:
                        conn.execute(text("SET LOCAL statement_timeout = '5000ms'"))
                        for sql, params, _ in queries:
                            plan = conn.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params).scalar()
                            plans.append(plan)
                key = ("ppt" if primary else "legacy") + ":" + name
                results[key] = {"median": {field: statistics.median(row[field] for row in metrics) for field in metrics[0]},
                    "p95": {field: percentile([row[field] for row in metrics], .95) for field in metrics[0]},
                    "samples": metrics, "plans": plans,
                    "response_sha256": hashlib.sha256(json.dumps(serialized, sort_keys=True).encode()).hexdigest()}
        return {"generated_at": datetime.now(UTC).isoformat(), "projection": projection,
                "postgres": version, "counts": counts, "repetitions": repetitions,
                "cache_policy": "response caches bypassed; database/OS caches not flushed", "cases": results,
                "ingestion": ingestion_cost(engine, repetitions) if measure_ingestion else None}
    finally:
        settings.catalog_current_prices_enabled, settings.ppt_primary_enabled = original
        engine.dispose()


def ingestion_cost(engine, repetitions):
    """Opt-in synthetic inserts are rolled back; sequence values are consumed."""
    with Session(engine) as db:
        card_id = db.scalar(select(PriceObservation.card_id).where(PriceObservation.provider == "tcgapi").limit(1))
    result = {}
    for maintain in (False, True):
        samples = []
        for _ in range(repetitions):
            with Session(engine) as db:
                db.execute(text("SET LOCAL statement_timeout = '5000ms'"))
                token = "benchmark-" + uuid.uuid4().hex
                db.add(PriceObservation(card_id=card_id, provider="tcgapi", provider_card_id=token,
                    variant_id=token, fingerprint=token, price=1, currency="USD",
                    observed_at=datetime.now(UTC), provider_updated_at=datetime.now(UTC)))
                started = time.perf_counter()
                if maintain: refresh_candidates(db, [card_id])
                else: db.flush()
                samples.append((time.perf_counter() - started) * 1000)
                db.rollback()
        result["with_projection" if maintain else "source_only"] = {"median_ms": statistics.median(samples), "samples_ms": samples}
    return result


def compare(baseline, current):
    failures = []
    if baseline["projection"] or not current["projection"]:
        failures.append("Comparison requires history baseline and projected result")
    if baseline["counts"] != current["counts"]:
        failures.append("Dataset counts changed; comparison invalid")
    for name, value in current["cases"].items():
        if not name.endswith(":pokemon"):
            def scans_history(node):
                if isinstance(node, dict):
                    return node.get("Relation Name") == "price_observations" or any(scans_history(v) for v in node.values())
                return isinstance(node, list) and any(scans_history(v) for v in node)
            if scans_history(value["plans"]):
                failures.append(f"{name}: projected current-price read scans history")
        if value["response_sha256"] != baseline["cases"][name]["response_sha256"]:
            failures.append(f"{name}: response parity mismatch")
        old = baseline["cases"][name]["median"]["sql_ms"]
        new = value["median"]["sql_ms"]
        if name.endswith(("broad_price_desc", "broad_price_asc")) and new > old * .5:
            failures.append(f"{name}: broad sort improvement below 50%")
        elif new - old > 20 and new > old * 1.1:
            failures.append(f"{name}: regression exceeds 10% and 20ms")
    return failures


def main():
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projection", choices=["on", "off"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--measure-ingestion", action="store_true", help="Measure rolled-back synthetic writes in the disposable database")
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    url = os.environ.get("CATALOG_TEST_DATABASE_URL")
    if args.compare and not args.explain:
        parser.error("--compare requires --explain to verify the absence of historical scans")
    if not url or args.repetitions < 3:
        parser.error("Explicit CATALOG_TEST_DATABASE_URL and at least three repetitions are required")
    logging.basicConfig(level=logging.INFO)
    try:
        result = benchmark(url, projection=args.projection == "on", repetitions=args.repetitions, explain=args.explain, measure_ingestion=args.measure_ingestion)
        if args.compare:
            result["acceptance_failures"] = compare(json.loads(args.compare.read_text()), result)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2))
        print(json.dumps({"output": str(args.output), "acceptance_failures": result.get("acceptance_failures", [])}))
        return int(bool(result.get("acceptance_failures")))
    except Exception as exc:
        logger.exception("Catalog benchmark failed error=%s: %s", type(exc).__name__, exc)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
