"""Opt-in local PPT pilot; run from backend with PYTHONPATH=.

Uses the real quota limiter and retains a receipt across invocations. Never
enables scheduled ingestion. Payloads contain public product data, not headers
or credentials. The 30-credit pilot ceiling is additional to account limits.
"""
import argparse
import fcntl
import json
from pathlib import Path

import httpx
from redis import Redis

from app.providers.ppt import PPTClient, PPTQuota


def verify_saved(directory):
    """Replay saved responses only into the fixed, disposable pilot database."""
    from datetime import UTC, datetime
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session
    from fastapi import Response
    from app.config import get_settings
    from app.models import Card, Set, MarketHistory, PPTProduct, PPTHistory, PPTCurrentQuote, PriceObservation
    from app.services.ppt_ingestion import map_product, ingest
    from app.services.ppt_prices import pricing_data
    from app.routers.cards import get_card_prices

    settings = get_settings()
    settings.postgres_host = None
    settings.database_url = "postgresql+psycopg://ppt_pilot:ppt_local_test@127.0.0.1:15432/ppt_pilot"
    settings.ppt_primary_enabled = True  # This process and disposable database only.
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    command.upgrade(config, "head")
    engine = create_engine(settings.database_url)
    records = json.loads((directory / "requests.json").read_text())
    samples = []
    with Session(engine, expire_on_commit=False) as db:
        if not db.get(Set, "pilot-legacy"):
            db.add(Set(id="pilot-legacy", name="Pilot legacy"))
            db.flush()
            db.add(Card(id="pilot-legacy", set_id="pilot-legacy", name="Legacy", number="1"))
            db.flush()
            db.add(MarketHistory(card_id="pilot-legacy", printing="Normal", day=datetime.now(UTC).date(),
                                 market_price=99, fetched_at=datetime.now(UTC)))
            db.commit()
        for record in records:
            if record["resource"] == "sets" or not record.get("payload_file"):
                continue
            for payload in json.loads((directory / record["payload_file"]).read_text()):
                language = record["params"]["language"]
                kind = "cards" if record["resource"] == "cards" else "sealed"
                product = map_product(db, payload, language, kind)
                assert product.status == "matched", product.match_method
                ingest(db, product, payload)
                db.commit()
                models = (Card, Set, PPTProduct, PriceObservation, PPTHistory, PPTCurrentQuote, MarketHistory)
                counts = lambda: {m.__tablename__: db.scalar(select(func.count()).select_from(m)) for m in models}
                before = counts()
                ingest(db, product, payload)
                db.commit()
                assert counts() == before, "Repeat ingestion created duplicates"
                result = pricing_data(db, product.card_id)
                assert result["ppt_mapped"] and result["provider_history"]
                public_response = get_card_prices(product.card_id, Response(), days=180, db=db)
                assert public_response.ppt_mapped and public_response.provider_quotes
                assert public_response.provider_history
                public_response.model_dump_json()
                primary = next(q for q in product.quotes if q.get("primary"))
                assert primary["price_change_7d"] is not None
                chunks = list(db.scalars(select(PPTHistory).where(PPTHistory.product_id == product.id)))
                dates = sorted({d for chunk in chunks for d in chunk.points})
                samples.append({"product": product.id, "name": payload["name"], "primary": primary,
                                "graded_quotes": [q for q in product.quotes if q.get("grade")],
                                "history_first": dates[0], "history_last": dates[-1],
                                "history_points": sum(len(chunk.points) for chunk in chunks),
                                "repeat_import": "passed"})
        assert db.scalar(select(MarketHistory.market_price).where(MarketHistory.card_id == "pilot-legacy")) == 99
        result = {"samples": samples, "counts": counts(), "legacy_preserved": True}
        (directory / "ingestion.json").write_text(json.dumps(result, indent=2))
        print(json.dumps({"products_verified": len(samples), "counts": result["counts"],
                          "legacy_preserved": True, "receipt": str(directory / "ingestion.json")}, indent=2))
    engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("resource", choices=["sets", "cards", "sealed-products", "verify-saved"])
    parser.add_argument("--language", choices=["english", "japanese"], default="english")
    parser.add_argument("--id")
    parser.add_argument("--set-id")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--ebay", action="store_true")
    args = parser.parse_args()
    directory = Path(__file__).resolve().parents[2] / ".system_generated/ppt-pilot"
    directory.mkdir(parents=True, exist_ok=True)
    if args.resource == "verify-saved":
        verify_saved(directory)
        return
    receipt = directory / "requests.json"
    records = json.loads(receipt.read_text()) if receipt.exists() else []
    cost = 1 if args.resource == "sets" else args.limit * (1 + args.history + args.ebay)
    if sum(r["reserved_credits"] for r in records) + cost > 30:
        raise SystemExit("Pilot ceiling reached; no request made")
    params = {"language": args.language, "limit": args.limit}
    for key, value in (("tcgPlayerId", args.id), ("setId", args.set_id),
                       ("includeHistory", args.history), ("includeEbay", args.ebay)):
        if value:
            params[key] = value
    record = {"resource": args.resource, "params": params, "reserved_credits": cost}
    records.append(record)
    receipt.write_text(json.dumps(records, indent=2))

    def response_hook(response):
        record["status"] = response.status_code
        if response.is_error:
            response.read()
            record["provider_error"] = response.text[:2000]
        record["quota_headers"] = {k: v for k, v in response.headers.items()
                                   if k.startswith("x-ratelimit-") or k == "x-api-calls-consumed"}
        receipt.write_text(json.dumps(records, indent=2))

    client = PPTClient(quota=PPTQuota(redis=Redis(host="127.0.0.1", port=16379)),
                       client=httpx.Client(timeout=30, follow_redirects=False,
                                           event_hooks={"response": [response_hook]}))
    try:
        rows = client.request(args.resource, **params)
        filename = f"response-{len(records):02d}.json"
        (directory / filename).write_text(json.dumps(rows, indent=2))
        record["payload_file"] = filename
        record["rows"] = len(rows)
        receipt.write_text(json.dumps(records, indent=2))
        print(json.dumps(record, indent=2))
        print(json.dumps([{k: row.get(k) for k in ("id", "tcgPlayerId", "name", "setId", "setName")}
                          for row in rows], indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    lock_dir = Path(__file__).resolve().parents[2] / ".system_generated/ppt-pilot"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with (lock_dir / "pilot.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        main()
