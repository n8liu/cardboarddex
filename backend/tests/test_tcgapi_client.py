"""Retirement and immutable identity compatibility replace retired HTTP contracts."""
from unittest.mock import Mock
import pytest
from app.tcgapi.client import TCGAPIClient, TCGAPIConfigurationError
from app.common.catalog_identity import local_card_id, parse_release_date, split_card_number


def test_retired_client_cannot_request_even_with_key(monkeypatch):
    network = Mock(side_effect=AssertionError('No legacy network access'))
    monkeypatch.setattr('httpx.get', network)
    with pytest.raises(TCGAPIConfigurationError, match='retired'):
        TCGAPIClient(api_key='ignored')
    network.assert_not_called()


def test_preserved_identity_helpers():
    assert local_card_id('123') == '123'
    assert len(local_card_id('x' * 100)) == 64
    assert split_card_number('12/100', None) == ('12', 100)
    assert parse_release_date('2026-01-01').isoformat() == '2026-01-01'
