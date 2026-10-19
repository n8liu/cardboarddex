from unittest.mock import Mock
from jobs import update_pokemon as job


def test_pokemon_uses_shared_ppt_and_preserves_ids(monkeypatch):
    monkeypatch.setattr(job, 'get_cards_for_pokemon', Mock(return_value=[Mock(id='old-card')]))
    ppt, ebay = Mock(return_value={'cards': 1}), Mock()
    monkeypatch.setattr(job, 'refresh_cards', ppt)
    monkeypatch.setattr(job, 'run_ebay_price_collection', ebay)
    db = Mock()
    result = job.update_cards_for_pokemon(db, 'Pikachu', ppt_only=True)
    assert result['total_cards'] == 1
    ppt.assert_called_once_with(db, ['old-card'], limit=8)
    ebay.assert_not_called()
