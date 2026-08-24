"""Monte Carlo: known worst cases, shuffle invariants, honest failure modes."""

from __future__ import annotations

import pytest

from trading_bot.backtesting.monte_carlo import (
    format_monte_carlo,
    monte_carlo_trades,
)


def test_shuffle_preserves_total_pnl():
    trades = [100.0, -50.0, 25.0, -25.0, 75.0]  # net +125
    r = monte_carlo_trades(trades, initial_equity=10_000, n_sims=500, method="shuffle")
    assert r.final_pnl_percentiles["p5"] == pytest.approx(125.0)
    assert r.final_pnl_percentiles["p50"] == pytest.approx(125.0)
    assert r.final_pnl_percentiles["p95"] == pytest.approx(125.0)
    assert r.prob_final_negative == 0.0


def test_worst_case_drawdown_is_found():
    # Both losses first -> cumulative -20: the worst possible ordering.
    trades = [-10.0, -10.0, 30.0, 5.0, 1.0]
    r = monte_carlo_trades(trades, initial_equity=1_000, n_sims=2_000, method="shuffle")
    assert r.drawdown_percentiles["worst"] == pytest.approx(20.0)
    assert r.losing_streak_percentiles["worst"] == 2


def test_bootstrap_varies_final_pnl():
    trades = [100.0, -80.0, 60.0, -40.0, 20.0, -10.0]
    r = monte_carlo_trades(trades, initial_equity=10_000, n_sims=2_000, method="bootstrap")
    assert r.final_pnl_percentiles["p5"] < r.final_pnl_percentiles["p95"]
    assert 0.0 < r.prob_final_negative < 1.0


def test_certain_ruin_detected():
    trades = [-100.0] * 10
    r = monte_carlo_trades(trades, initial_equity=500, n_sims=100,
                           method="shuffle", ruin_drawdown=0.5)
    assert r.prob_ruin == 1.0
    assert r.prob_final_negative == 1.0


def test_no_ruin_when_impossible():
    trades = [10.0, -5.0, 8.0, -3.0, 12.0]
    r = monte_carlo_trades(trades, initial_equity=100_000, n_sims=200, ruin_drawdown=0.5)
    assert r.prob_ruin == 0.0


def test_deterministic_with_seed():
    trades = [10.0, -20.0, 15.0, -5.0, 30.0, -25.0]
    a = monte_carlo_trades(trades, initial_equity=1_000, n_sims=500, seed=7)
    b = monte_carlo_trades(trades, initial_equity=1_000, n_sims=500, seed=7)
    assert a == b


def test_input_validation():
    with pytest.raises(ValueError, match="meaningful trade sample"):
        monte_carlo_trades([1.0, 2.0], initial_equity=1_000)
    with pytest.raises(ValueError, match="method"):
        monte_carlo_trades([1.0] * 10, initial_equity=1_000, method="magic")
    with pytest.raises(ValueError, match="ruin_drawdown"):
        monte_carlo_trades([1.0] * 10, initial_equity=1_000, ruin_drawdown=1.5)


def test_report_renders_with_disclaimer():
    r = monte_carlo_trades([10.0, -5.0, 8.0, -3.0, 12.0], initial_equity=1_000, n_sims=100)
    text = format_monte_carlo(r)
    assert "MONTE CARLO" in text
    assert "not guarantees" in text
