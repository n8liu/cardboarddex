import pytest

from app.services.asking_prices import robust_asking_price


def test_extreme_listing_among_normal_ones_is_ignored():
    asks = [180.0, 200.0, 210.0, 195.0, 17_500_000.0]
    assert robust_asking_price(asks) == pytest.approx(197.5)


def test_single_listing_stands_unless_it_breaks_the_reference_cap():
    assert robust_asking_price([240.0], reference=60.0) == 240.0
    assert robust_asking_price([17_500_000.0], reference=60.0) is None


def test_empty_and_non_positive_prices_give_none():
    assert robust_asking_price([]) is None
    assert robust_asking_price([0.0, -5.0]) is None


def test_two_far_apart_listings_take_the_lower_ask():
    assert robust_asking_price([100.0, 17_500_000.0]) == 100.0


def test_band_drops_lowball_listings_too():
    assert robust_asking_price([1.0, 300.0, 310.0, 320.0]) == 310.0


def test_reference_cap_ignored_without_a_reference():
    assert robust_asking_price([50_000.0]) == 50_000.0
    assert robust_asking_price([50_000.0], reference=0) == 50_000.0
