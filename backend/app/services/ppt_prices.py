"""Stored provider quotes and series for public API responses."""
from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from app.config import get_settings
from app.models import PPTProduct, PPTHistory
from app.services.ppt_ingestion import digest


def pricing_data(db, card_id, days=180):
    if not get_settings().ppt_primary_enabled:
        return {"provider_quotes": [], "provider_history": [], "ppt_mapped": False}
    products = list(db.scalars(select(PPTProduct).where(PPTProduct.card_id == card_id, PPTProduct.status == "matched")))
    quotes = []
    today = datetime.now(UTC).date()
    for product in products:
        for quote in product.quotes:
            quotes.append(dict(quote, fetched_at=product.last_success_at,
                               stale=quote["price_date"] < (today - timedelta(days=7)).isoformat()))
    cutoff = (today - timedelta(days=min(days, 730))).isoformat()
    series = {}
    for chunk in db.scalars(select(PPTHistory).where(PPTHistory.card_id == card_id, PPTHistory.month >= cutoff[:7])):
        key = digest([chunk.product_id, chunk.dimensions])
        item = series.setdefault(key, dict(chunk.dimensions, id=key, points=[], fetched_at=chunk.fetched_at))
        item["fetched_at"] = max(item["fetched_at"], chunk.fetched_at)
        item["points"].extend(dict(point, date=d) for d, point in chunk.points.items() if cutoff <= d <= today.isoformat())
    for item in series.values():
        item["points"].sort(key=lambda p: p["date"])
    return {"provider_quotes": quotes, "provider_history": list(series.values()),
            "ppt_mapped": any(p.last_success_at for p in products)}


def primary_quotes(db, card_ids):
    if not get_settings().ppt_primary_enabled or not card_ids:
        return {}
    today = datetime.now(UTC).date()
    result = {}
    for p in db.scalars(select(PPTProduct).where(PPTProduct.card_id.in_(card_ids), PPTProduct.status == "matched")):
        quote = next((q for q in p.quotes if q.get("primary") and not q.get("grade")
                      and q["price_date"] >= (today - timedelta(days=7)).isoformat()), None)
        if quote:
            result[p.card_id] = dict(quote, fetched_at=p.last_success_at)
    return result


def market_history(db, card_id, days=30):
    data = pricing_data(db, card_id, days + 7)
    quote = next((q for q in data["provider_quotes"] if q["primary"] and not q["grade"] and not q["stale"]), None)
    if not quote:
        return None
    series = next((s for s in data["provider_history"] if s["metric"] == "market"
                   and s["printing"] == quote["printing"] and s["condition"] == quote["condition"]), None)
    points = series["points"] if series else []
    from datetime import date
    baseline_day = (date.fromisoformat(quote["price_date"]) - timedelta(days=days)).isoformat()
    baseline = next((p["price"] for p in points if p["date"] == baseline_day), None)
    change = (quote["price"] / baseline - 1) * 100 if baseline else None
    return {"card_id": card_id, "printing": quote["printing"], "condition": quote["condition"],
        "days": days, "currency": "USD", "provider": quote["provider"], "status": "ready",
        "synced_at": quote["fetched_at"], "coverage_start": points[0]["date"] if points else None,
        "coverage_end": points[-1]["date"] if points else None, "return_end": quote["price_date"],
        "return_percent": change, "complete_return_window": change is not None,
        "previous_price": baseline, "comparison_price": quote["price"],
        "price_change_amount": round(quote["price"] - baseline, 2) if baseline else None,
        "comparison_source": "pokemonpricetracker_history" if baseline else None,
        "points": [{"date": p["date"], "market_price": p["price"], "sales_volume": p["sales_count"], "avg_sales_price": None} for p in points]}


def sales_activity(db, days=30, q=""):
    """Count explicitly reported raw sales, not snapshots, listings or history points."""
    from app.models import Card, Set
    from app.common.formatters import escape_like
    from sqlalchemy import or_
    today = datetime.now(UTC).date()
    start = today - timedelta(days=days - 1)
    query = select(PPTHistory, PPTProduct.quotes, Card.name, Set.name).join(
        PPTProduct, PPTHistory.product_id == PPTProduct.id).join(Card, PPTHistory.card_id == Card.id).join(Set, Card.set_id == Set.id).where(
        PPTProduct.status == "matched", PPTHistory.month >= start.isoformat()[:7],
        PPTHistory.dimensions["metric"].as_string() == "market")
    if q.strip():
        pattern = f"%{escape_like(q.strip())}%"
        query = query.where(or_(Card.name.ilike(pattern, escape="\\"), Set.name.ilike(pattern, escape="\\")))
    totals = {}
    # Stream monthly chunks, not the whole catalog's price payloads.
    for chunk, quotes, name, set_name in db.execute(query.execution_options(yield_per=50)):
        primary = next((x for x in quotes if x.get("primary") and not x.get("grade")), None)
        if not primary or any(chunk.dimensions[k] != primary[k] for k in ("printing", "condition", "language")):
            continue
        for d, point in chunk.points.items():
            if not start.isoformat() <= d <= today.isoformat() or point.get("sales_count") is None:
                continue
            item = totals.setdefault(chunk.card_id, {"card_id": chunk.card_id, "name": name, "set_name": set_name,
                "sales": 0, "reported_rows": 0, "last_reported_day": d, "synced_at": chunk.fetched_at})
            item["sales"] += point["sales_count"]
            item["reported_rows"] += 1
            item["last_reported_day"] = max(item["last_reported_day"], d)
            item["synced_at"] = max(item["synced_at"], chunk.fetched_at)
    rows = sorted(totals.values(), key=lambda x: (-x["sales"], x["card_id"]))
    return {"days": days, "start": start, "end": today,
        "synced_at": max((x["synced_at"] for x in rows), default=None),
        "status": "ready" if rows else "no_matches" if q.strip() else "no_sales",
        "total_sales": sum(x["sales"] for x in rows) if rows else None,
        "products_with_sales_data": len(rows), "items": rows[:50],
        "source": "Pokémon Price Tracker reported raw sales",
        "coverage": "Synced primary printing and condition only. Missing volume is unknown. Graded aggregates and asking listings are excluded."}


def label_market_sources(db, items):
    """Bounded page-level labels; sorting already uses the shared SQL rule."""
    quotes = primary_quotes(db, [item.id for item in items])
    for item in items:
        if item.market_price is not None:
            item.market_source = "pokemonpricetracker" if item.id in quotes else "tcgapi"
        if item.id in quotes:
            item.last_updated_at = datetime.fromisoformat(quotes[item.id]["price_date"] + "T00:00:00+00:00")
