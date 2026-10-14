"""Opt-in real PostgreSQL/Redis tests. URLs must name disposable infrastructure."""
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from redis import Redis
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import Base
from app.models import Card, Set
from app.providers.limiter import DailyRequestLimiter, ProviderRequestLimitExceeded, scheduled_budget
from app.services import passive_refresh as refresh


@pytest.fixture
def infra(monkeypatch):
    db_url=os.getenv('REFRESH_TEST_DATABASE_URL'); redis_url=os.getenv('REFRESH_TEST_REDIS_URL')
    if not db_url or not redis_url: pytest.skip('Requires disposable PostgreSQL and Redis URLs')
    if db_url.startswith('postgresql://'): db_url = 'postgresql+psycopg://' + db_url[len('postgresql://'):]
    name='refresh_'+uuid.uuid4().hex
    admin=create_engine(db_url)
    with admin.begin() as c:c.execute(text(f'CREATE SCHEMA {name}'))
    engine=create_engine(db_url,connect_args={'options':f'-csearch_path={name}'})
    Base.metadata.create_all(engine)
    raw=Redis.from_url(redis_url,decode_responses=True)
    class NamespacedRedis:
        def get(self,key):return raw.get(name+':'+key)
        def set(self,key,value,**kwargs):return raw.set(name+':'+key,value,**kwargs)
        def mget(self,keys):return raw.mget([name+':'+key for key in keys])
        def delete(self,*keys):return raw.delete(*(name+':'+key for key in keys))
        def eval(self,script,n,*args):return raw.eval(script,n,*(name+':'+key for key in args[:n]),*args[n:])
    redis=NamespacedRedis()
    settings=Settings(_env_file=None, price_collection_card_limit=8, passive_priority_card_count=1500)
    monkeypatch.setattr(refresh,'get_settings',lambda:settings)
    monkeypatch.setattr(refresh,'get_durable_redis',lambda:redis)
    monkeypatch.setattr(refresh,'interest_scores',lambda now:{})
    with Session(engine) as db:
        db.add(Set(id='s',name='Set',release_date=date(2026,1,1)))
        db.add_all(Card(id=f'{i:05}',name=f'Card {i}',number=str(i),rarity='Rare',set_id='s') for i in range(2000))
        db.commit()
        yield db,redis,settings
    for key in raw.scan_iter(name+':*'):raw.delete(key)
    raw.close();engine.dispose()
    with admin.begin() as c:c.execute(text(f'DROP SCHEMA {name} CASCADE'))
    admin.dispose()


def test_seven_days_healthy_checks_all_1500_for_both_providers(infra):
    db,redis,_=infra; start=1_800_000_000 // 86400 * 86400
    catalog={p:set() for p in refresh.PROVIDERS}
    for step in range(7*48):
        for provider in refresh.PROVIDERS:
            now=start+step*1800+(900 if provider=='ebay' else 0)
            limiter=DailyRequestLimiter('unused',provider,2000 if provider=='tcgapi' else 500,
                max_per_second=0,now=lambda:now,redis_client=redis)
            def collect(session,*,card_ids):
                for _ in range(2 if provider=='tcgapi' else 1):limiter.acquire()
                if card_ids[0]>='01500':catalog[provider].add(card_ids[0])
                return {'cards':1,'provider_errors':0,'observations':0}
            result=refresh.run_scheduled_collection(db,provider,collect,now=now)
            assert result['successful_checks']==8
    report=refresh.coverage_report(redis,start+refresh.WEEK-1)
    for provider in refresh.PROVIDERS:
        assert report['providers'][provider]['checked_this_cycle']==1500
        assert report['providers'][provider]['remaining']==0
        assert report['providers'][provider]['catalog_advances']>=336
        assert len(catalog[provider])>=336
        assert report['providers'][provider]['quota']['scheduled_used'] <= (1500 if provider=='tcgapi' else 450)


def test_membership_frozen_across_restarts_and_weekly_missed_report(infra,monkeypatch):
    db,redis,_=infra; now=1_800_000_000
    def failing(session,*,card_ids):return {'cards':1,'provider_errors':1}
    refresh.run_scheduled_collection(db,'tcgapi',failing,now=now)
    original,states=refresh.load_state(redis)
    monkeypatch.setattr(refresh,'interest_scores',lambda at:{'01999':100})
    refresh.run_scheduled_collection(db,'ebay',failing,now=now+900)
    assert refresh.load_state(redis)[0]['members']==original['members']
    assert states['tcgapi']['checked']=={}
    report=refresh.coverage_report(redis,now+refresh.WEEK+1)
    assert report['providers']['tcgapi']['overdue']==1500
    refresh.run_scheduled_collection(db,'tcgapi',failing,now=now+refresh.WEEK+1)
    new,_=refresh.load_state(redis)
    assert new['members'][0]=='01999'
    assert new['history'][-1]['missed']=={'tcgapi':1500,'ebay':1500}


def test_crash_reservation_preserves_cursor_and_retry_without_false_success(infra):
    db,redis,_=infra; now=1_800_000_000
    def crash(session,*,card_ids):
        if card_ids[0]=='01500':raise RuntimeError('simulated process crash after reservation')
        return {'cards':1,'provider_errors':0}
    with pytest.raises(RuntimeError,match='simulated process crash'):
        refresh.run_scheduled_collection(db,'tcgapi',crash,now=now)
    cycle,states=refresh.load_state(redis);state=states['tcgapi']
    assert state['cursor']=='01500' and state['retries']['01500']==now+3600
    assert state['total_attempts']==8 and state['total_checked']==7
    assert redis.get(refresh.LOCK) is None
    # New coordinator/process reads durable membership and resumes instead of resetting.
    selected=refresh.select_batch(db,cycle,state,{},now+1800,8)
    assert '01501' in [cid for cid,_,_ in selected]
    assert '01500' not in [cid for cid,_,_ in selected]
    selected=refresh.select_batch(db,cycle,state,{},now+3600,8)
    assert ('01500','catalog_retry',False) in selected


def test_expired_lease_cannot_spend_requests_or_overwrite_new_owner(infra):
    db,redis,_=infra;now=1_800_000_000
    def replaced(session,*,card_ids):
        redis.set(refresh.LOCK,'new-owner',ex=900)
        limiter=DailyRequestLimiter('unused','tcgapi',2000,max_per_second=0,redis_client=redis)
        with pytest.raises(ProviderRequestLimitExceeded,match='lease_expired'):limiter.acquire()
        return {'cards':1,'provider_errors':0}
    assert refresh.run_scheduled_collection(db,'tcgapi',replaced,now=now)=={'skipped':'lease_expired'}
    assert redis.get(refresh.LOCK)=='new-owner'
    assert refresh.load_state(redis)[1]['tcgapi']['total_checked']==0


def test_atomic_sublimit_preserves_global_capacity_and_failed_permits_do_not_count(infra):
    _,redis,_=infra;now=1_800_000_000;day=int(now//86400)
    redis.set(refresh.LOCK,'token',ex=900)
    def request():
        limiter=DailyRequestLimiter('unused','ebay',500,max_per_second=0,now=lambda:now,redis_client=redis)
        try:
            with scheduled_budget('ebay',5,refresh.LOCK,'token'):limiter.acquire()
            return True
        except ProviderRequestLimitExceeded:return False
    with ThreadPoolExecutor(max_workers=16) as pool:
        assert sum(pool.map(lambda _:request(),range(40)))==5
    assert redis.get(f'cardboarddex:ebay:requests:{day}')=='5'
    assert redis.get(f'cardboarddex:ebay:scheduled_requests:{day}')=='5'
    manual=DailyRequestLimiter('unused','ebay',500,max_per_second=0,now=lambda:now,redis_client=redis)
    manual.acquire()
    assert redis.get(f'cardboarddex:ebay:requests:{day}')=='6'
    assert redis.get(f'cardboarddex:ebay:scheduled_requests:{day}')=='5'
    redis.set(f'cardboarddex:ebay:requests:{day}',500)
    with pytest.raises(ProviderRequestLimitExceeded,match='daily_limit'):manual.acquire()
    assert redis.get(f'cardboarddex:ebay:requests:{day}')=='500'


def test_empty_success_counts_but_errors_do_not_and_quota_stop_preserves_cursor(infra):
    db,redis,_=infra;now=1_800_000_000
    def empty(session,*,card_ids):return {'cards':1,'provider_errors':0,'observations':0}
    result=refresh.run_scheduled_collection(db,'ebay',empty,now=now)
    assert result['successful_checks']==8 and result['observations']==0
    before=refresh.load_state(redis)[1]['ebay']
    redis.set(f'cardboarddex:ebay:scheduled_requests:{int(now//86400)}',450)
    assert refresh.run_scheduled_collection(db,'ebay',empty,now=now+1800)=={'skipped':'daily_limit'}
    assert refresh.load_state(redis)[1]['ebay']==before


def test_seven_day_outage_reports_missed_coverage_and_advances_catalog(infra):
    db,redis,_=infra;start=1_800_000_000
    def failing(session,*,card_ids):return {'cards':1,'provider_errors':1}
    for step in range(7*48):
        result=refresh.run_scheduled_collection(db,'tcgapi',failing,now=start+step*1800)
        assert result['successful_checks']==0
    report=refresh.coverage_report(redis,start+refresh.WEEK+1)['providers']['tcgapi']
    assert report['overdue']==1500 and report['checked_this_cycle']==0
    assert report['catalog_advances']>=168
    assert report['retry_count']<=refresh.MAX_RETRIES


def test_redis_restart_keeps_cycle_and_cursor(infra):
    import subprocess
    db,redis,_=infra;now=1_800_000_000
    container=os.getenv('REFRESH_TEST_REDIS_CONTAINER')
    if container!='cardboarddex-refresh-test-redis':pytest.skip('Requires explicitly named disposable Redis container')
    refresh.run_scheduled_collection(db,'tcgapi',lambda session,**kw:{'cards':1,'provider_errors':0},now=now)
    before=refresh.load_state(redis)
    subprocess.run(['docker','restart',container],check=True,capture_output=True)
    import time
    for _ in range(100):
        probe=subprocess.run(['docker','exec',container,'redis-cli','ping'],capture_output=True,text=True)
        if probe.returncode==0 and probe.stdout.strip()=='PONG':break
        time.sleep(.1)
    else:pytest.fail('Disposable Redis did not become ready after restart')
    # A new connection after restart must read the same AOF-backed state.
    assert refresh.load_state(redis)==before
    assert before[1]['tcgapi']['cursor']=='01500'
