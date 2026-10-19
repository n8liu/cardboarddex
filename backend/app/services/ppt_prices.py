"""Stored provider quotes and series for public API responses."""
from datetime import UTC, datetime, timedelta
from heapq import nsmallest
from sqlalchemy import select
from app.config import get_settings
from app.models import PPTProduct, PPTHistory
from app.services.ppt_ingestion import digest


def graded_sales_activity(db, q=""):
    """Rank stored graded snapshots; counts have no verified fixed time window."""
    from sqlalchemy import or_
    from app.common.formatters import escape_like
    from app.models import Card, Set
    from app.services.ppt_ingestion import day

    result = {"status": "provider_disabled", "synced_at": None,
        "coverage": "Provider-reported coverage; not a selected-period total. "
                    "Graded sales reported by Pokémon Price Tracker across its sources. "
                    "Missing counts are unknown. Rankings cover synced cards only.",
        "products_with_sales_data": 0, "items": []}
    if not get_settings().ppt_primary_enabled:
        return result
    query = select(PPTProduct.card_id, PPTProduct.metadata_payload["ebay"], PPTProduct.metadata_payload["graded_synced_at"].as_string(),
                   PPTProduct.last_success_at, Card.name, Card.image_url, Set.name).join(
        Card, Card.id == PPTProduct.card_id).join(Set, Set.id == Card.set_id).where(
        PPTProduct.status == "matched", PPTProduct.segment.in_(["english:cards", "japanese:cards"]),
        PPTProduct.last_success_at.is_not(None))
    if q.strip():
        pattern = f"%{escape_like(q.strip())}%"
        query = query.where(or_(Card.name.ilike(pattern, escape="\\"), Set.name.ilike(pattern, escape="\\")))
    # A card may have multiple mappings: use its newest snapshot, never sum duplicates.
    query = query.order_by(PPTProduct.card_id, PPTProduct.last_success_at.desc(), PPTProduct.id)
    now = datetime.now(UTC)
    previous_card = None
    rows = []
    for card_id, ebay, graded_at, synced_at, name, image_url, set_name in db.execute(query.execution_options(yield_per=50)):
        if card_id == previous_card:
            continue
        previous_card = card_id
        grades = ebay.get("salesByGrade") if isinstance(ebay, dict) else None
        if not isinstance(grades, dict):
            continue
        breakdown = []
        for grade, data in sorted(grades.items()):
            count = data.get("count") if isinstance(data, dict) else None
            if type(count) is not int or count < 0:
                continue
            try:
                sold = day(data.get("lastSaleDate"))
            except ValueError:
                # day() logs the exact malformed provider value and error.
                sold = None
            breakdown.append({"grade": grade, "sales": count,
                              "last_sale_date": sold.isoformat() if sold and sold <= now.date() else None})
        if not breakdown:
            continue
        synced_at = datetime.fromisoformat(graded_at) if graded_at else None
        if synced_at and synced_at.tzinfo is None:
            synced_at = synced_at.replace(tzinfo=UTC)
        dates = [g["last_sale_date"] for g in breakdown if g["last_sale_date"]]
        rows.append({"card_id": card_id, "name": name, "set_name": set_name, "image_url": image_url,
                     "sales": sum(g["sales"] for g in breakdown), "grades": breakdown,
                     "last_sale_date": max(dates, default=None), "synced_at": synced_at,
                     "stale": not graded_at or synced_at < now - timedelta(days=7)})
        result["products_with_sales_data"] += 1
        if synced_at:
            result["synced_at"] = max(result["synced_at"] or synced_at, synced_at)
        # Bound retained payloads even when ranking the whole synced catalog.
        if len(rows) > 100:
            rows = nsmallest(50, rows, key=lambda row: (-row["sales"], row["card_id"]))
    result["items"] = nsmallest(50, rows, key=lambda row: (-row["sales"], row["card_id"]))
    result["status"] = "ready" if rows else "no_matches" if q.strip() else "not_synced"
    return result


def pricing_data(db, card_id, days=180, *, stored=None):
    if not get_settings().ppt_primary_enabled:
        from app.services.market_history import legacy_series
        return {"provider_quotes": [], "provider_history": [], "market_quotes": [],
                "market_history_series": legacy_series(db, card_id, days, stored), "ppt_mapped": False}
    products = stored["products"] if stored is not None else list(db.scalars(select(PPTProduct).where(PPTProduct.card_id == card_id, PPTProduct.status == "matched")))
    quotes = []
    today = datetime.now(UTC).date()
    for product in products:
        for quote in product.quotes:
            quotes.append(dict(quote, fetched_at=product.last_success_at,
                               stale=bool(quote.get("historical_only")) or quote["price_date"] < (today - timedelta(days=7)).isoformat()))
    for quote in quotes:
        if quote["stale"]:
            for period in ("24h", "7d", "30d"):
                quote["price_change_" + period] = None
    cutoff = (today - timedelta(days=min(days, 730))).isoformat()
    series = {}
    matched_ids = {p.id for p in products}
    for chunk in (stored["history"] if stored is not None else db.scalars(select(PPTHistory).where(PPTHistory.card_id == card_id, PPTHistory.month >= cutoff[:7]))):
        if chunk.product_id not in matched_ids:
            continue
        key = digest([chunk.product_id, chunk.dimensions])
        item = series.setdefault(key, dict(chunk.dimensions, id=key, points=[], fetched_at=chunk.fetched_at))
        item["fetched_at"] = max(item["fetched_at"], chunk.fetched_at)
        item["points"].extend(dict(point, date=d) for d, point in chunk.points.items() if cutoff <= d <= today.isoformat())
    for item in series.values():
        item["points"].sort(key=lambda p: p["date"])
    provider_history = list(series.values())
    original_history = [dict(s, points=list(s["points"])) for s in provider_history]
    # Include a dated quote even when a provider omits today's history point.
    for quote in quotes:
        if quote.get("grade"):
            continue
        item = next((s for s in provider_history if all(s.get(k) == quote.get(k) for k in
            ("language", "currency", "printing", "condition", "grade", "metric"))), None)
        if item is None:
            item = {k: quote.get(k) for k in ("provider", "language", "currency", "printing", "condition", "grade", "metric")}
            item.update(id=digest([card_id, item]), points=[], fetched_at=quote["fetched_at"])
            provider_history.append(item)
        if not any(p["date"] == quote["price_date"] for p in item["points"]):
            item["points"].append(dict(date=quote["price_date"], price=quote["price"], sales_count=None))
            item["points"].sort(key=lambda p: p["date"])
    from app.services.market_history import unified_history
    return {"provider_quotes": quotes, "provider_history": original_history,
            "market_quotes": quotes, "market_history_series": unified_history(db, card_id, provider_history, days, stored),
            "ppt_mapped": any(p.last_success_at for p in products)}


def primary_quotes(db, card_ids):
    if not get_settings().ppt_primary_enabled or not card_ids:
        return {}
    today = datetime.now(UTC).date()
    result = {}
    for p in db.scalars(select(PPTProduct).where(PPTProduct.card_id.in_(card_ids), PPTProduct.status == "matched")):
        quote = next((q for q in p.quotes if q.get("primary") and not q.get("grade")
                      and q["price_date"] <= today.isoformat()), None)
        if quote:
            result[p.card_id] = dict(quote, fetched_at=p.last_success_at, stale=bool(quote.get("historical_only")) or quote["price_date"] < (today - timedelta(days=7)).isoformat())
    for quote in result.values():
        if quote["stale"]:
            for period in ("24h", "7d", "30d"):
                quote["price_change_" + period] = None
    return result


def market_history(db, card_id, days=30):
    if not get_settings().ppt_primary_enabled:
        return None
    data = pricing_data(db, card_id, days + 7)
    quote = next((q for q in data["provider_quotes"] if q["primary"] and not q["grade"] and not q["stale"]), None)
    if not quote:
        return None
    series = next((s for s in data["market_history_series"] if s["metric"] == "market"
                   and s["printing"] == quote["printing"] and s["condition"] == quote["condition"]), None)
    points = series["points"] if series else []
    from datetime import date
    baseline_day = (date.fromisoformat(quote["price_date"]) - timedelta(days=days)).isoformat()
    baseline = next((p["price"] for p in points if p["date"] == baseline_day and p.get("source") == "pokemonpricetracker"), None)
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
