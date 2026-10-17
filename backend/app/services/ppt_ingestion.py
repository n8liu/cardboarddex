"""Pure normalization and transactional storage. Never mutates legacy prices."""
import hashlib
import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from sqlalchemy import delete, func, or_, select
from app.models import Card, Set, ProviderCardState, PriceObservation, PPTProduct, PPTHistory, PPTCurrentQuote, PPTCheckpoint
from app.providers.ppt import PROVIDER

logger = logging.getLogger(__name__)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def norm(value):
    return " ".join(str(value or "").casefold().split())


def quote_condition(value, printing, language):
    """Remove only known provider printing/language suffixes, never guess NM."""
    label = str(value or "Unknown")
    for condition in ("Near Mint", "Lightly Played", "Moderately Played", "Heavily Played", "Damaged"):
        candidates = {condition, f"{condition} {printing}"}
        if language == "japanese":
            candidates |= {f"{candidate} - Japanese" for candidate in tuple(candidates)}
        if norm(label) in {norm(candidate) for candidate in candidates}:
            return condition
    return label


def price(value):
    if value is None:
        return None
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or result >= 1_000_000_000:
            raise ValueError("price outside supported range")
        return float(result)
    except (InvalidOperation, ValueError) as exc:
        logger.error("PPT invalid price value=%r error=%s: %s", value, type(exc).__name__, exc)
        raise ValueError("Invalid PPT price") from exc


def day(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        logger.error("PPT invalid date value=%r: %s", value, exc)
        raise


def normalize(payload, language, kind, today=None):
    today = today or datetime.now(UTC).date()
    quotes, series = [], []
    base = {"provider": PROVIDER, "language": language, "currency": "USD"}

    def dimensions(printing, condition, grade, metric):
        return dict(base, printing=printing, condition=condition, grade=grade, metric=metric)

    def add_series(dim, rows, key):
        if len(rows) > 400:
            raise ValueError("PPT history exceeds bounded daily window")
        points = {}
        for row in rows:
            d = day(row.get("date"))
            if not d or d > today or d < today - timedelta(days=180):
                continue
            count = row.get("volume", row.get("count"))
            if count is not None and (not isinstance(count, int) or count < 0):
                raise ValueError("Invalid PPT sales count")
            points[d.isoformat()] = {"price": price(row.get(key)), "sales_count": count}
        if points:
            series.append({"dimensions": dim, "points": points})

    def add_quote(dim, value, at, primary=False, **extra):
        value, as_of = price(value), day(at)
        if value is None or value <= 0 or not as_of or as_of > today:
            return
        quotes.append(dict(dim, price=value, price_date=as_of.isoformat(), primary=primary, **extra))

    if kind == "sealed":
        dim = dimensions("Unopened", "Unopened", None, "market")
        add_series(dim, payload.get("priceHistory") or [], "unopenedPrice")
        add_quote(dim, payload.get("unopenedPrice"), payload.get("lastScrapedAt") or payload.get("updatedAt"), True)
    else:
        prices = payload.get("prices") or {}
        primary = prices.get("primaryPrinting")
        variants = payload.get("variants") or {}
        history = (payload.get("priceHistory") or {}).get("variants") or {}
        for printing, conditions in history.items():
            for condition, data in conditions.items():
                add_series(dimensions(printing, condition, None, "market"), data.get("history") or [], "market")
        for printing, data in variants.items():
            # Do not silently relabel LP/MP quotes as Near Mint.
            condition = quote_condition(data.get("conditionUsed"), printing, language)
            dim = dimensions(printing, condition, None, "market")
            add_quote(dim, data.get("marketPrice"), prices.get("lastUpdated"), printing == primary,
                      low_price=price(data.get("lowPrice")), corrected=bool(prices.get("priceWasCorrected")))
        # Top-level price has no trustworthy condition if variants are absent.
        if not variants:
            add_quote(dimensions(primary or "Unknown", "Unknown", None, "market"), prices.get("market"), prices.get("lastUpdated"), True)
        ebay = payload.get("ebay") or {}
        for grade, data in (ebay.get("salesByGrade") or {}).items():
            if not re.fullmatch(r"(?:psa|cgc|bgs|sgc)[0-9]+(?:_[0-9]+)?", grade):
                continue  # Keep unsupported premium tiers in original metadata; never merge into a base grade.
            updated = data.get("lastMarketUpdate")
            sold = day(data.get("lastSaleDate"))
            as_of = day(updated)
            if sold and as_of and today - timedelta(days=7) <= sold <= today and today - timedelta(days=7) <= as_of <= today:
                add_quote(dimensions(None, None, grade, "median_7d"), data.get("marketPriceMedian7Day"), updated,
                    last_sale_date=sold.isoformat(), sources=data.get("salesBySource") or {},
                    smart_price_outlier=bool((ebay.get("smartPriceOutlierByGrade") or {}).get(grade)),
                    labels=data.get("labels"))
        for grade, points in (ebay.get("priceHistory") or {}).items():
            add_series(dimensions(None, None, grade, "daily_average"),
                       [dict(value, date=key) for key, value in points.items()], "average")
    # Changes require exact same printing, condition and metric at the exact date.
    for quote in quotes:
        points = next((s["points"] for s in series if all(quote.get(k) == v for k, v in s["dimensions"].items())), {})
        for label, days in (("24h", 1), ("7d", 7), ("30d", 30), ("90d", 90)):
            baseline = points.get((day(quote["price_date"]) - timedelta(days=days)).isoformat(), {}).get("price")
            quote[f"price_change_{label}"] = round((quote["price"] / baseline - 1) * 100, 4) if baseline and quote["price"] > 0 else None
    return quotes, series


def map_product(db, payload, language, kind, set_metadata=None):
    db.flush()  # Make earlier page mappings visible even with autoflush disabled.
    provider_id = str(payload.get("tcgPlayerId") or "")
    if not provider_id or len(provider_id) > 128 or not payload.get("name") or not payload.get("setName"):
        raise ValueError("PPT product identity is incomplete")
    key = f"{language}:{kind}:{provider_id}"
    existing = db.get(PPTProduct, key)
    if existing:
        return existing
    segment = f"{language}:{kind}"
    product = PPTProduct(id=key, provider_id=provider_id, segment=segment, status="quarantined",
                         metadata_payload=payload, quotes=[], failures=0)
    db.add(product)
    sets = list(db.scalars(select(Set).where(func.lower(Set.name) == norm(payload["setName"]))))
    sets = [s for s in sets if (s.series == "Pokemon Japan") == (language == "japanese")]
    number = str(payload.get("cardNumber") or "").split("/")[0].strip()
    # Only explicit, provider-issued TCGplayer identifiers count as external IDs.
    # Legacy local IDs and filenames are not evidence of TCGplayer identity.
    identity_index = db.get(PPTCheckpoint, f"legacy-id:{language}:{provider_id}")
    legacy_ids = identity_index.payload.get("card_ids", []) if identity_index else []
    explicit = list(db.execute(select(Card, Set).join(Set, Card.set_id == Set.id).where(Card.id.in_(legacy_ids)))) if legacy_ids else []
    explicit = [(card, card_set) for card, card_set in explicit
        if (card_set.series == "Pokemon Japan") == (language == "japanese")]
    if explicit:
        card, card_set = explicit[0]
        valid = (len(explicit) == 1 and norm(card.name) == norm(payload["name"])
                 and (kind == "sealed" and not card.rarity or kind == "cards" and number and norm(card.number) == norm(number)))
        occupied = db.scalar(select(PPTProduct.id).where(PPTProduct.card_id == card.id, PPTProduct.status == "matched"))
        if valid and not occupied:
            product.card_id, product.status, product.match_method = card.id, "matched", "verified_tcgplayer_id"
        else:
            product.match_method = "external_id_conflict"
        return product

    candidates = list(db.scalars(select(Card).where(Card.set_id.in_([s.id for s in sets])))) if sets else []
    exact = [c for c in candidates if norm(c.name) == norm(payload["name"]) and
             (kind == "sealed" and not c.number or kind == "cards" and number and norm(c.number) == norm(number))]
    if len(exact) == 1 and db.scalar(select(PPTProduct.id).where(PPTProduct.card_id == exact[0].id, PPTProduct.status == "matched")):
        product.match_method = "multiple_provider_products"
        return product
    if len(exact) == 1:
        product.card_id, product.status, product.match_method = exact[0].id, "matched", "language_set_name_number"
        return product
    # A same-number/name conflict must be reviewed, not duplicated as a new product.
    conflicts = [c for c in candidates if norm(c.name) == norm(payload["name"]) or (number and norm(c.number) == norm(number))]
    if len(sets) > 1 or conflicts or (kind == "cards" and not number):
        product.match_method = "ambiguous_identity"
        return product
    # Existing external mappings are never guessed from legacy IDs or image URLs.
    if sets:
        card_set = sets[0]
    else:
        set_key = str(payload.get("setId") or "")
        if not set_key:
            product.match_method = "missing_set_identity"
            return product
        sid = "ppt-set-" + digest([language, set_key])[:32]
        card_set = db.get(Set, sid)
        if card_set is None:
            card_set = Set(id=sid, name=payload["setName"], series="Pokemon Japan" if language == "japanese" else (set_metadata or {}).get("series"),
                           release_date=day((set_metadata or {}).get("releaseDate")))
            db.add(card_set)
            db.flush()
    cid = "ppt-" + digest(key)[:40]
    db.add(Card(id=cid, name=payload["name"], set_id=card_set.id, number=number if kind == "cards" else "",
                rarity=(payload.get("rarity") or "Unknown") if kind == "cards" else None,
                image_url=payload.get("imageCdnUrl800") or payload.get("imageCdnUrl400") or payload.get("imageUrl")))
    db.flush()
    product.card_id, product.status, product.match_method = cid, "matched", "new_provider_identity"
    return product


def ingest(db, product, payload, now=None):
    now = now or datetime.now(UTC)
    if product.status != "matched" or not product.card_id:
        return
    language, kind = product.segment.split(":")
    if str(payload.get("tcgPlayerId")) != product.provider_id:
        raise ValueError("PPT response identity differs from requested product")
    prior = product.metadata_payload
    if any(norm(payload.get(field)) != norm(prior.get(field)) for field in ("name", "setName", "cardNumber")):
        product.status, product.match_method = "quarantined", "provider_identity_changed"
        db.execute(delete(PPTCurrentQuote).where(PPTCurrentQuote.product_id == product.id))
        return
    quotes, series = normalize(payload, language, kind, now.date())
    if "ebay" not in payload:
        quotes.extend(q for q in product.quotes if q.get("grade") and q["price_date"] >= (now.date() - timedelta(days=7)).isoformat())
    for series_item in series:
        dim = series_item["dimensions"]
        months = {}
        for d, point in series_item["points"].items():
            months.setdefault(d[:7], {})[d] = point
        for month, points in months.items():
            key = digest([product.id, dim, month])
            chunk = db.get(PPTHistory, key)
            if chunk is None:
                db.add(PPTHistory(id=key, product_id=product.id, card_id=product.card_id, month=month,
                                 dimensions=dim, points=points, fetched_at=now))
            else:
                chunk.points = {**chunk.points, **points}
                chunk.fetched_at = now
    db.execute(delete(PPTCurrentQuote).where(PPTCurrentQuote.product_id == product.id))
    # Only current quotes create feed observations. Historical dates never do.
    for quote in quotes:
        identity = {k: quote[k] for k in ("provider", "language", "printing", "condition", "grade", "metric", "currency")}
        fingerprint = digest([product.id, identity, quote["price"], quote["price_date"]])
        db.add(PPTCurrentQuote(fingerprint=fingerprint, product_id=product.id, price_date=day(quote["price_date"])))
        stored = db.scalar(select(PriceObservation).where(PriceObservation.fingerprint == fingerprint))
        if stored:
            stored.payload = dict(quote, market_price_as_of=quote["price_date"],
                update_type="graded_aggregate" if quote["grade"] else "market_update")
            continue
        grade_match = re.fullmatch(r"([a-z]+)([0-9]+(?:_[0-9]+)?)", quote["grade"] or "")
        db.add(PriceObservation(fingerprint=fingerprint, card_id=product.card_id, provider=PROVIDER,
            provider_card_id=product.provider_id, variant_id=digest(identity), condition=quote["condition"], printing=quote["printing"],
            grading_company=grade_match[1].upper() if grade_match else None,
            grade=Decimal(grade_match[2].replace("_", ".")) if grade_match else None,
            price=quote["price"], currency="USD", provider_updated_at=datetime.combine(day(quote["price_date"]), datetime.min.time(), UTC),
            observed_at=now, payload=dict(quote, market_price_as_of=quote["price_date"],
                update_type="graded_aggregate" if quote["grade"] else "market_update")))
    product.quotes = quotes
    product.primary_price = next((q["price"] for q in quotes if q.get("primary") and not q.get("grade")), None)
    # Bound current snapshot: historical arrays already live in monthly chunks.
    product.metadata_payload = {k: v for k, v in payload.items() if k not in {"priceHistory", "ebay"}}
    if payload.get("ebay"):
        product.metadata_payload["ebay"] = {k: v for k, v in payload["ebay"].items() if k not in {"priceHistory", "soldListings"}}
    product.last_success_at, product.retry_at, product.failures = now, None, 0
    db.flush()


def index_legacy_identities(db, limit=500):
    """One bounded scan of explicit legacy identifiers, instead of JSON table scans per product."""
    state = db.get(PPTCheckpoint, "legacy-id-index")
    if state and state.payload.get("complete"):
        return True
    if state is None:
        state = PPTCheckpoint(key="legacy-id-index", payload={"after": 0})
        db.add(state)
    rows = db.execute(select(ProviderCardState.id, ProviderCardState.card_id, Set.series,
        ProviderCardState.payload["card"]["tcgPlayerId"].as_string(),
        ProviderCardState.payload["card"]["data"]["tcgPlayerId"].as_string())
        .join(Card, ProviderCardState.card_id == Card.id).join(Set, Card.set_id == Set.id)
        .where(ProviderCardState.provider == "tcgapi", ProviderCardState.id > state.payload["after"])
        .order_by(ProviderCardState.id).limit(limit)).all()
    for _, cid, series, direct, nested in rows:
        provider_id = str(direct or nested or "")
        if not provider_id or len(provider_id) > 128:
            continue
        language = "japanese" if series == "Pokemon Japan" else "english"
        key = f"legacy-id:{language}:{provider_id}"
        entry = db.get(PPTCheckpoint, key)
        if entry is None:
            entry = PPTCheckpoint(key=key, payload={"card_ids": [cid]})
            db.add(entry)
            db.flush()
        else:
            entry.payload = {"card_ids": sorted(set(entry.payload["card_ids"] + [cid]))}
    state.payload = {"after": rows[-1][0] if rows else state.payload["after"], "complete": len(rows) < limit}
    return state.payload["complete"]
