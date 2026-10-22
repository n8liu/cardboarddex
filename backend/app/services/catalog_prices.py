"""Transactional, bounded current-price projection; no provider access."""
import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import Date, and_, case, delete, func, insert, literal, or_, select, text, true
from sqlalchemy.orm import aliased
from app.models import Card, CatalogPriceCandidate as C, CatalogPriceProjectionState as State, PPTCurrentQuote, PriceObservation as O

VERSION = 2
BATCH_SIZE = 250


def lock_cards(db, card_ids):
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL lock_timeout = '5000ms'"))
        for card_id in sorted(set(card_ids)):
            key = int.from_bytes(hashlib.sha256(("catalog-price:" + card_id).encode()).digest()[:8], "big", signed=True)
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def expected_candidates(db, card_ids):
    columns = [O.card_id, O.provider, O.id.label("observation_id"), O.fingerprint, O.price,
               O.currency, O.condition, O.printing, O.provider_updated_at, O.observed_at]
    order = (O.provider_updated_at.desc().nullslast(), O.observed_at.desc(), O.id.desc())
    latest = select(*columns, func.row_number().over(partition_by=O.card_id, order_by=order).label("position")).where(
        O.card_id.in_(card_ids), O.provider == "tcgapi", O.grading_company.is_(None)).subquery()
    tcg = select(*[latest.c[c.key] for c in C.__table__.columns if c.key not in {"ppt_price_date", "selected"}],
                 literal(None, type_=Date).label("ppt_price_date")).where(latest.c.position == 1)
    ppt = select(*columns, PPTCurrentQuote.price_date.label("ppt_price_date")).join(
        PPTCurrentQuote, PPTCurrentQuote.fingerprint == O.fingerprint).where(
        O.card_id.in_(card_ids), O.provider == "pokemonpricetracker", O.grading_company.is_(None),
        O.payload["primary"].as_boolean().is_(True))
    return mark_selected([dict(row) for row in db.execute(tcg).mappings()] + [dict(row) for row in db.execute(ppt).mappings()])


def mark_selected(rows):
    """Flag each card's PPT-primary price, in the same order as candidate_join."""
    best = {}
    for row in rows:
        row["selected"] = False
        rank = (row["provider"] == "pokemonpricetracker", row["provider_updated_at"] is not None,
                row["provider_updated_at"], row["observed_at"], row["observation_id"])
        if row["card_id"] not in best or rank > best[row["card_id"]][0]:
            best[row["card_id"]] = (rank, row)
    for _, row in best.values():
        row["selected"] = True
    return rows


def refresh_candidates(db, card_ids):
    ids = sorted(set(card_ids))
    if not ids:
        return
    lock_cards(db, ids)
    db.flush()
    rows = expected_candidates(db, ids)
    db.execute(delete(C).where(C.card_id.in_(ids)))
    if rows:
        db.execute(insert(C), rows)


def commit_prices(db):
    """TCG writers call this instead of commit; both writes succeed or roll back."""
    ids = set(db.info.get("catalog_price_cards", ())) | {row.card_id for row in list(db.new) + list(db.dirty)
           if isinstance(row, O) and row.provider == "tcgapi"}
    refresh_candidates(db, ids)
    db.commit()
    db.info.pop("catalog_price_cards", None)


def candidate_join(*, broad=False, as_of=None, dialect=None):
    from app.config import get_settings
    primary = get_settings().ppt_primary_enabled
    day = as_of or datetime.now(UTC).date()
    eligible = C.provider == "tcgapi"
    if primary:
        eligible = or_(eligible, C.provider == "pokemonpricetracker")
    order = (case((C.provider == "pokemonpricetracker", 0), else_=1),
             C.provider_updated_at.desc().nullslast(), C.observed_at.desc(), C.observation_id.desc())
    if not primary:
        row = aliased(C)
        return row, row, and_(row.card_id == Card.id, row.provider == "tcgapi")
    if broad:
        # Selection is precomputed on write (mark_selected), so broad reads never
        # rank candidates and price sorts can walk ix_catalog_price_selected.
        row = aliased(C)
        return row, row, and_(row.card_id == Card.id, row.selected)
    if dialect == "postgresql":
        rows = select(C.price, C.currency, C.provider_updated_at).where(
            C.card_id == Card.id, eligible).order_by(*order).limit(1).correlate(Card).lateral()
        return rows.c, rows, true()
    row = aliased(C)
    selected = select(C.observation_id).where(C.card_id == Card.id, eligible).order_by(*order).limit(1).correlate(Card).scalar_subquery()
    return row, row, and_(row.card_id == Card.id, row.observation_id == selected)


def require_ready(db):
    state = db.get(State, VERSION)
    if state is None or not state.complete or state.verified_at is None:
        raise RuntimeError("Catalog current prices require a completed, verified backfill; keep CATALOG_CURRENT_PRICES_ENABLED=false")


def backfill_batch(db, *, restart=False):
    state = db.scalar(select(State).where(State.version == VERSION).with_for_update())
    if state is None:
        state = State(version=VERSION, complete=False)
        db.add(state)
        db.flush()
    if restart:
        state.after_card_id, state.complete, state.verified_at = None, False, None
    if state.complete:
        return 0
    stmt = select(Card.id).order_by(Card.id).limit(BATCH_SIZE)
    if state.after_card_id is not None:
        stmt = stmt.where(Card.id > state.after_card_id)
    ids = list(db.scalars(stmt))
    refresh_candidates(db, ids)
    if ids:
        state.after_card_id = ids[-1]
    state.complete = len(ids) < BATCH_SIZE
    state.verified_at = None
    db.commit()
    return len(ids)


def verify_projection(db):
    """Caller uses one repeatable-read transaction; comparison covers all candidates."""
    after, checked, mismatches = None, 0, []
    while True:
        stmt = select(Card.id).order_by(Card.id).limit(BATCH_SIZE)
        if after is not None:
            stmt = stmt.where(Card.id > after)
        ids = list(db.scalars(stmt))
        if not ids:
            break
        expected = expected_candidates(db, ids)
        actual = [dict(row) for row in db.execute(select(C.__table__).where(C.card_id.in_(ids))).mappings()]
        key = lambda row: (row["card_id"], row["provider"], row["observation_id"])
        e, a = {key(row): row for row in expected}, {key(row): row for row in actual}
        mismatches.extend(sorted({k[0] for k in e.keys() | a.keys() if e.get(k) != a.get(k)}))
        checked += len(ids)
        after = ids[-1]
    # Orphan candidates are impossible with enforced FKs, but detect them in SQLite too.
    orphan = list(db.scalars(select(C.card_id).outerjoin(Card, C.card_id == Card.id).where(Card.id.is_(None)).distinct()))
    return {"checked_cards": checked, "mismatched_cards": sorted(set(mismatches + orphan))}
