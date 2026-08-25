"""Phase 12: strategy-P&L correlation and the diversification verdict."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.portfolio.correlation import (
    correlation_summary,
    pnl_correlation_matrix,
    rolling_pnl_correlation,
)
from trading_bot.portfolio.portfolio import compare_portfolio

DAYS = pd.date_range("2025-01-01", periods=250, freq="1D").date


def series(values):
    return pd.Series(values, index=DAYS[: len(values)])


def test_correlation_matrix_extremes():
    rng = np.random.default_rng(1)
    a = series(rng.normal(0, 100, 250))
    m = pnl_correlation_matrix({"A": a, "B": a.copy(), "C": -a})
    assert m.loc["A", "B"] == pytest.approx(1.0)
    assert m.loc["A", "C"] == pytest.approx(-1.0)


def test_alignment_fills_non_trading_days_with_zero():
    a = series([100.0] * 250)
    b = series([50.0] * 200)   # stops trading earlier
    m = pnl_correlation_matrix({"A": a, "B": b})
    assert m.shape == (2, 2)   # aligned without error; missing B days -> 0 P&L


def test_rolling_correlation_window():
    rng = np.random.default_rng(2)
    a = series(rng.normal(0, 100, 250))
    b = series(rng.normal(0, 100, 250))
    roll = rolling_pnl_correlation(a, b, window_days=30)
    assert len(roll) == 250
    assert roll.iloc[:14].isna().all()      # min_periods = window//2
    assert roll.dropna().between(-1, 1).all()


def test_correlation_summary_pairs():
    rng = np.random.default_rng(3)
    streams = {
        "MNQ": series(rng.normal(20, 100, 250)),
        "HL:BTC": series(rng.normal(20, 100, 250)),
    }
    s = correlation_summary(streams)
    assert "MNQ|HL:BTC" in s["pairs"]
    pair = s["pairs"]["MNQ|HL:BTC"]
    assert pair["rolling_max"] >= pair["full_sample"] >= pair["rolling_min"]


# ---- portfolio verdicts ---------------------------------------------------------
def _positive_stream(seed, mean=50.0, std=200.0, n=250):
    rng = np.random.default_rng(seed)
    return series(rng.normal(mean, std, n))


def test_equal_quality_uncorrelated_streams_diversify():
    # Same P&L distribution, decorrelated by a half-period roll: the textbook
    # case where diversification genuinely helps — verdict must say so.
    rng = np.random.default_rng(10)
    vals = rng.normal(50, 200, 250)
    a = series(vals)
    b = series(np.roll(vals, 125))
    result = compare_portfolio({"A": a, "B": b}, initial_equity=100_000)
    assert result.diversification_helps, result.verdict
    best = result.per_market[result.best_single]
    assert result.combined["sharpe"] > best["sharpe"]
    assert result.combined["max_drawdown_pct"] <= best["max_drawdown_pct"]


def test_identical_streams_concentrate():
    a = _positive_stream(30)
    result = compare_portfolio({"A": a, "B": a.copy()}, initial_equity=100_000)
    assert not result.diversification_helps
    assert result.verdict.startswith("CONCENTRATE")


def test_losing_streams_no_basis():
    result = compare_portfolio(
        {"A": _positive_stream(40, mean=-50), "B": _positive_stream(41, mean=-50)},
        initial_equity=100_000,
    )
    assert result.verdict.startswith("NO BASIS")


def test_weights_validation():
    a, b = _positive_stream(1), _positive_stream(2)
    with pytest.raises(ValueError, match="at least two"):
        compare_portfolio({"A": a}, initial_equity=100_000)
    with pytest.raises(ValueError, match="cover exactly"):
        compare_portfolio({"A": a, "B": b}, initial_equity=100_000,
                          weights={"A": 1.0})
    with pytest.raises(ValueError, match="positive"):
        compare_portfolio({"A": a, "B": b}, initial_equity=100_000,
                          weights={"A": 0.0, "B": 0.0})


def test_weights_are_normalized():
    a, b = _positive_stream(5), _positive_stream(6)
    result = compare_portfolio({"A": a, "B": b}, initial_equity=100_000,
                               weights={"A": 3.0, "B": 1.0})
    assert result.weights["A"] == pytest.approx(0.75)
    assert result.weights["B"] == pytest.approx(0.25)
