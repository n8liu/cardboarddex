from copy import deepcopy
from scripts.benchmark_catalog import compare, percentile


def test_benchmark_rejects_fast_but_wrong_or_historical_results():
    case = {"median": {"sql_ms": 100}, "response_sha256": "same", "plans": []}
    before = {"projection": False, "counts": {"cards": 1}, "cases": {"legacy:broad_price_desc": case}}
    after = deepcopy(before)
    after["projection"] = True
    result = after["cases"]["legacy:broad_price_desc"]
    result["median"]["sql_ms"] = 40
    assert compare(before, after) == []
    result["response_sha256"] = "wrong"
    assert any("parity" in failure for failure in compare(before, after))
    result["response_sha256"] = "same"
    result["plans"] = [{"Plan": {"Plans": [{"Relation Name": "price_observations"}]}}]
    assert any("scans history" in failure for failure in compare(before, after))
    result["plans"] = []
    result["median"]["sql_ms"] = 60
    assert any("below 50%" in failure for failure in compare(before, after))


def test_p95_uses_nearest_rank_with_small_sample():
    assert percentile([1, 2, 3, 4, 5, 6, 100], .95) == 100
