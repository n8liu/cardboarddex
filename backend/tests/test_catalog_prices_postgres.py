"""Explicitly opt-in PostgreSQL validation in disposable, uniquely named schemas."""
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session
from app.database import Base
from app.models import Card, Set, PriceObservation as O, CatalogPriceCandidate as C
from app.services.catalog_prices import lock_cards, refresh_candidates, verify_projection


@pytest.fixture
def infrastructure():
    url = os.environ.get("CATALOG_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set CATALOG_TEST_DATABASE_URL to an explicitly disposable PostgreSQL database")
    schema = "catalog_test_" + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Set(id="s", name="Set"))
        db.flush()
        db.add(Card(id="c", set_id="s", name="Card", number="1", image_url=""))
        db.commit()
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


def add(db, fingerprint, price):
    db.add(O(card_id="c", provider="tcgapi", provider_card_id="p", variant_id="v",
             fingerprint=fingerprint, price=price, currency="USD", observed_at=datetime.now(UTC)))


def test_backfill_waits_for_ingestion_and_does_not_overwrite(infrastructure):
    engine = infrastructure
    acquired, waiting, release = threading.Event(), threading.Event(), threading.Event()
    def writer():
        with Session(engine) as db:
            lock_cards(db, ["c"])
            add(db, "new", 20)
            refresh_candidates(db, ["c"])
            acquired.set()
            assert release.wait(3)
            db.commit()
    def backfill():
        assert acquired.wait(3)
        with Session(engine) as db:
            waiting.set()
            refresh_candidates(db, ["c"])
            db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(writer), pool.submit(backfill)
        assert waiting.wait(3)
        try:
            time.sleep(.1)
            assert not second.done()
        finally:
            release.set()
        first.result(3)
        second.result(3)
    with Session(engine) as db:
        assert db.scalar(select(C.price)) == 20
        assert verify_projection(db)["mismatched_cards"] == []


def test_partial_uniqueness_and_transaction_rollback(infrastructure):
    from sqlalchemy.exc import IntegrityError
    with Session(infrastructure) as db:
        add(db, "old", 10)
        refresh_candidates(db, ["c"])
        db.commit()
        add(db, "new", 20)
        refresh_candidates(db, ["c"])
        db.rollback()
        assert db.scalar(select(C.price)) == 10
        original = db.scalar(select(C))
        db.add(C(**{column.name: getattr(original, column.name) for column in C.__table__.columns
                    if column.name != "observation_id"}, observation_id=999))
        with pytest.raises(IntegrityError): db.flush()
        db.rollback()
        assert db.scalar(select(C.price)) == 10


def test_migration_preserves_catalog_schema_and_rows(infrastructure):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    # Load the revision by file path: installed alembic is a different package.
    import importlib.util
    spec = importlib.util.spec_from_file_location("catalog_price_migration", "alembic/versions/0011_catalog_prices.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with infrastructure.begin() as conn:
        migration.op = Operations(MigrationContext.configure(conn))
        migration.downgrade()
        before = {name: (inspect(conn).get_columns(name), inspect(conn).get_indexes(name),
                        conn.execute(text(f"SELECT count(*) FROM {name}")).scalar()) for name in ("cards", "sets")}
        migration.upgrade()
        after = {name: (inspect(conn).get_columns(name), inspect(conn).get_indexes(name),
                       conn.execute(text(f"SELECT count(*) FROM {name}")).scalar()) for name in ("cards", "sets")}
        for name in before:
            assert str(before[name]) == str(after[name])
        assert conn.execute(text("SELECT complete FROM catalog_price_projection_state")).scalar() is False
