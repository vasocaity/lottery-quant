"""Tests for the walk-forward backtest statistics (baseline + significance)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.model import binom_p_value, summarize_walk_forward, walk_forward_backtest  # noqa: E402


def test_binom_p_value_at_expected_is_near_half():
    # observing exactly the mean number of hits is not surprising
    p = binom_p_value(observed=20, n=1000, p=0.02)  # mean = 20
    assert 0.4 < p < 0.6


def test_binom_p_value_far_above_mean_is_significant():
    # 60 hits when ~20 expected => extremely unlikely by chance
    assert binom_p_value(observed=60, n=1000, p=0.02) < 0.001


def test_binom_p_value_below_mean_is_not_significant():
    assert binom_p_value(observed=5, n=1000, p=0.02) > 0.99


def test_summarize_baseline_and_lift():
    # exactly random performance: hits == expected => lift 1.0, p ~ 0.5
    n_pred, space = 1000, 1000
    hits = {1: 1, 20: 20}  # k/space * n_pred
    rep = summarize_walk_forward(hits, n_pred, space)
    by_k = {row["k"]: row for row in rep["by_k"]}
    assert by_k[20]["expected_hits"] == 20.0
    assert by_k[20]["baseline_rate_pct"] == 2.0
    assert abs(by_k[20]["lift"] - 1.0) < 1e-6
    assert not by_k[20]["beats_random_p05"]


def test_random_series_does_not_beat_baseline():
    """End-to-end smoke test: on a synthetic uniform-random history the model
    must NOT show a statistically significant edge for any k."""
    import numpy as np
    from datetime import date, timedelta

    rng = np.random.default_rng(0)
    start = date(2000, 1, 1)
    draws = []
    for i in range(120):
        draws.append({
            "date": (start + timedelta(days=i * 15)).isoformat(),
            "back3": str(int(rng.integers(0, 1000))).zfill(3),
            "last2": str(int(rng.integers(0, 100))).zfill(2),
        })

    rep = walk_forward_backtest(draws, start_frac=0.6, retrain_every=20, ks=(20,))
    row = rep["by_k"][0]
    assert row["n_predictions"] > 0
    # pure noise: should not clear the p<0.05 bar
    assert not row["beats_random_p05"], f"false signal on random data: {row}"
