import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('monitor_ingestion',Path(__file__).with_name('monitor_ingestion.py'))
monitor=importlib.util.module_from_spec(spec);spec.loader.exec_module(monitor)


def healthy(now=1000):
    return {'at':now,'containers':{'worker':{'running':True,'oom':False,'oom_kill':0,'restarts':0}},
            'api_ready':True,'available_mib':200,'swap_in_mib_s':0,'iowait_pct':0,'backup_age_seconds':100}


def test_transient_pressure_and_probe_failure_do_not_pause():
    a=healthy();a.update(api_ready=False,available_mib=100)
    assert monitor.regression({},a)==[]
    b=healthy(1060)
    assert monitor.regression(a,b)==[]
    assert b['pressure_since'] is None and b['api_failures']==0


def test_sustained_pressure_api_failures_and_oom_are_visible():
    a=healthy();a.update(api_ready=False,available_mib=100)
    monitor.regression({},a)
    b=healthy(1060);b.update(api_ready=False,available_mib=100);monitor.regression(a,b)
    c=healthy(1301);c.update(api_ready=False,available_mib=100)
    c['containers']['worker']['oom_kill']=1
    reasons=monitor.regression(b,c)
    assert any('five minutes' in x for x in reasons)
    assert any('three consecutive' in x for x in reasons)
    assert any('OOM' in x for x in reasons)


def test_worker_restart_or_missing_backup_requires_pause():
    a=healthy();b=healthy(1060);b['containers']['worker']['restarts']=1;b['backup_age_seconds']=24000
    reasons=monitor.regression(a,b)
    assert len(reasons)==2
