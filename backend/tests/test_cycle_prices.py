from unittest.mock import Mock
from jobs import cycle_prices as job


def test_manual_cycle_respects_provider_selection(monkeypatch):
    ppt, ebay = Mock(return_value={'cards': 1}), Mock(return_value={'cards': 1})
    monkeypatch.setattr(job, 'refresh_cards', ppt)
    monkeypatch.setattr(job, 'run_ebay_price_collection', ebay)
    db = Mock()
    assert job.run_price_cycle(db, card_id='card', ppt_limit=0) == {'ebay': {'cards': 1}}
    ppt.assert_not_called()
    ebay.assert_called_once_with(db, card_ids=['card'], limit=8)
    ebay.reset_mock()
    job.run_price_cycle(db, card_id='card', ebay_limit=0)
    ppt.assert_called_once_with(db, ['card'], limit=8)
    ebay.assert_not_called()


def test_old_cycle_task_is_inert():
    assert job.cycle_prices.run() == {'status': 'retired'}
