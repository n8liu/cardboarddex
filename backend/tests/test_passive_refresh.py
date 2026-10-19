from datetime import date, datetime, UTC
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Card, Set, PriceObservation
from app.services import passive_refresh as refresh


@pytest.fixture
def db():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Set(id='set', name='Set'))
        session.add_all(Card(id=f'{i:04}', name=f'Card {i}', number=str(i), rarity='Rare', set_id='set') for i in range(30))
        session.commit()
        yield session
    engine.dispose()


def cycle(now=1_800_000_000):
    return {'starts': now, 'ends': now + refresh.WEEK, 'members': [f'{i:04}' for i in range(20)], 'history': []}


def test_percentiles_equal_ties_and_missing():
    values = refresh.percentiles({'a': 10, 'b': 10, 'c': 20, 'd': None})
    assert values == {'a': .25, 'b': .25, 'c': 1., 'd': 0.}
    assert refresh.percentiles({'a': 7, 'b': 7}) == {'a': .5, 'b': .5}
    assert refresh.percentiles({'a': None}) == {'a': 0.}


def test_rank_weights_latest_positive_price_and_id_ties(db):
    db.get(Set, 'set').release_date = date(2020, 1, 1)
    db.add(Set(id='new', name='New', release_date=date(2026, 1, 1)))
    db.get(Card, '0001').set_id = 'new'
    for index, price in enumerate([100, 20, 0]):
        db.add(PriceObservation(card_id='0002', provider='tcgapi', provider_card_id='0002',
            variant_id='v', fingerprint=str(index), price=price, currency='USD',
            observed_at=datetime(2026, 1, index + 1, tzinfo=UTC)))
    # Non-USD and graded prices never contribute to priority.
    db.add(PriceObservation(card_id='0003', provider='tcgapi', provider_card_id='0003', variant_id='v',
        fingerprint='graded', price=9999, currency='USD', grading_company='PSA', grade=10))
    db.commit()
    ranked = refresh.rank_priority(db, {'0000': 100}, 30)
    assert ranked[:3] == ['0000', '0002', '0001']
    assert ranked[3:] == sorted(ranked[3:])
    # Latest positive price, not historical maximum, determines order.
    db.add(PriceObservation(card_id='0004', provider='tcgapi', provider_card_id='0004', variant_id='v',
        fingerprint='p4', price=50, currency='USD'))
    db.commit()
    ranked = refresh.rank_priority(db, {'0000': 100}, 30)
    assert ranked.index('0004') < ranked.index('0002')


def test_sealed_and_code_cards_are_ineligible(db):
    db.get(Card, '0000').rarity = None
    db.get(Card, '0001').name = 'Code Card Pack'
    db.commit()
    assert not {'0000', '0001'} & set(refresh.rank_priority(db, {}, 30))


def test_batch_has_five_weekly_two_hot_one_catalog_without_duplicates(db):
    c = cycle(); state = refresh.initial_progress()
    batch = refresh.select_batch(db, c, state, {'0000': 9, '0001': 8}, c['starts'], 8)
    assert len({cid for cid, _, _ in batch}) == 8
    assert [lane for _, lane, _ in batch].count('hot') == 2
    assert [lane for _, lane, _ in batch].count('priority') == 5
    assert [lane for _, lane, _ in batch].count('catalog') == 1


def test_hot_success_satisfies_coverage_and_three_hour_interval(db):
    c = cycle(); state = refresh.initial_progress()
    state['checked'] = {cid: c['starts'] for cid in c['members']}
    early = refresh.select_batch(db, c, state, {}, c['starts'] + 10799, 8)
    assert all(lane == 'catalog' for _, lane, _ in early)
    later = refresh.select_batch(db, c, state, {}, c['starts'] + 10800, 8)
    assert sum(lane == 'hot' for _, lane, _ in later) == 2


def test_cursor_wrap_and_independent_provider_progress(db):
    c = cycle(); state = refresh.initial_progress()
    state['cursor'] = '0028'
    state['checked'] = {cid: c['starts'] for cid in c['members']}
    batch = refresh.select_batch(db, c, state, {}, c['starts'] + 1, 8)
    assert batch[:2] == [('0029', 'catalog', False), ('0020', 'catalog', True)]
    other = refresh.initial_progress()
    assert refresh.select_batch(db, c, other, {}, c['starts'], 8)[-1][0] == '0020'


def test_retry_is_delayed_and_cannot_stall_catalog_cursor(db):
    c=cycle(); state=refresh.initial_progress(); now=c['starts']
    state['retries']['0020']=now + 3600
    state['catalog_turn']=1
    early=refresh.select_batch(db,c,state,{},now,8)
    assert '0020' not in [cid for cid, _, _ in early]
    later=refresh.select_batch(db,c,state,{},now+3600,8)
    assert later[-1]==('0020','catalog_retry',False)
    refresh.reserve_attempt(state,'0020','catalog_retry',False,now+3600)
    next_batch=refresh.select_batch(db,c,state,{},now+5400,8)
    assert next_batch[-1][1]=='catalog' and next_batch[-1][0]!='0020'


def test_retry_queue_is_bounded_and_overflow_reported():
    state=refresh.initial_progress()
    for i in range(refresh.MAX_RETRIES+10):
        refresh.reserve_attempt(state,str(i),'catalog',False,1_800_000_000+i)
    assert len(state['retries']) == refresh.MAX_RETRIES
    assert state['retry_overflow']==10


def test_interest_seven_buckets_and_bounded_retention(monkeypatch):
    redis=MagicMock(); redis.zrevrange.return_value=[('card',2)]
    monkeypatch.setattr(refresh,'get_redis',lambda:redis)
    assert refresh.interest_scores(100*86400)=={'card':14}
    assert redis.zrevrange.call_count==7
    refresh.record_card_interest(redis,'card',100*86400)
    redis.pipeline.return_value.expire.assert_called_once_with(f'{refresh.PREFIX}:interest:100',8*86400)


def test_scheduled_entrypoints_use_coordinator(monkeypatch):
    from jobs import collect_prices, collect_ebay_prices
    runner=MagicMock(return_value={'cards':0})
    monkeypatch.setattr(refresh,'run_scheduled_collection',runner)
    assert collect_prices.collect_prices.run()['status'] == 'retired'
    for module, task, provider in [(collect_ebay_prices,collect_ebay_prices.collect_ebay_prices,'ebay')]:
        monkeypatch.setattr(module,'SessionLocal',MagicMock())
        assert task.run()=={'cards':0}
        assert runner.call_args.args[1]==provider


def test_unchanged_checks_never_create_new_comps_but_new_listing_does(db):
    from jobs.collect_prices import _observation
    from sqlalchemy import func, select
    args=dict(card_id='0000',provider='ebay',provider_card_id='listing1',variant_id='raw',price='10.00')
    assert _observation(db,**args,provider_updated_at=datetime(2026,1,1,tzinfo=UTC))
    db.commit()
    assert not _observation(db,**args,provider_updated_at=datetime(2026,1,2,tzinfo=UTC))
    assert _observation(db,**{**args,'price':'11.00'},provider_updated_at=datetime(2026,1,2,tzinfo=UTC))
    db.commit()
    assert _observation(db,**{**args,'provider_card_id':'listing2'},provider_updated_at=datetime(2026,1,2,tzinfo=UTC))
    db.commit()
    assert db.scalar(select(func.count()).select_from(PriceObservation))==3


@pytest.mark.parametrize("primary", [False, True])
def test_verified_projection_ranking_does_not_scan_history(db, monkeypatch, primary):
    from sqlalchemy import event
    from app.models import CatalogPriceProjectionState, CatalogPriceCandidate
    from app.services.catalog_prices import VERSION
    monkeypatch.setattr(refresh.get_settings(), "ppt_primary_enabled", primary)
    db.add(CatalogPriceProjectionState(version=VERSION, complete=True, verified_at=datetime.now(UTC)))
    for cid, provider, amount, oid in [("0002", "tcgapi", 100, 1),
                                      ("0002", "pokemonpricetracker", 10, 2),
                                      ("0003", "tcgapi", 50, 3),
                                      ("0004", "tcgapi", 9999, 4)]:
        db.add(CatalogPriceCandidate(card_id=cid, provider=provider, observation_id=oid,
            fingerprint=str(oid), price=amount, currency="EUR" if cid == "0004" else "USD",
            observed_at=datetime.now(UTC)))
    db.commit()
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        ranked = refresh.rank_priority(db, {"0000": 100}, 30)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)
    assert ranked[0] == "0000"
    assert (ranked.index("0003") < ranked.index("0002")) == primary
    assert ranked.index("0004") > ranked.index("0002")
    assert not any("price_observations" in statement for statement in statements)
