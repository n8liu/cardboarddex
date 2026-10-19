from unittest.mock import Mock
from jobs.sync_catalog import run_catalog_sync, sync_catalog


def test_retired_catalog_never_opens_provider_or_mutates_database():
    db, client = Mock(), Mock()
    assert run_catalog_sync(db, client=client)["status"] == "disabled"
    assert sync_catalog.run()["status"] == "retired"
    assert db.mock_calls == client.mock_calls == []
