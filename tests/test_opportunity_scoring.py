"""Opportunity scoring tests."""

from analytics.opportunities import compute_opportunity_score, frequency_score


def test_weights_sum_to_one_via_max_score() -> None:
    score = compute_opportunity_score(100, 100, 100, 100, 100, 100)
    assert score == 100.0


def test_conversion_relevance_weighted_highest() -> None:
    high_conv = compute_opportunity_score(0, 0, 100, 0, 0, 0)
    high_freq = compute_opportunity_score(100, 0, 0, 0, 0, 0)
    assert high_conv == 25.0
    assert high_freq == 20.0
    assert high_conv > high_freq


def test_frequency_score_caps_at_100() -> None:
    assert frequency_score(0, 10) == 0.0
    assert frequency_score(10, 10) == 100.0
    assert 0 < frequency_score(1, 10) < 100


def test_score_clamped() -> None:
    assert compute_opportunity_score(200, 200, 200, 200, 200, 200) == 100.0
