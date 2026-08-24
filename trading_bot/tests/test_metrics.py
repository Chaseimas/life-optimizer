"""Metrics: hand-computed values, degenerate inputs handled honestly."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.backtesting.metrics import (
    daily_stats,
    equity_curve,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
    summarize,
    trade_stats,
)

TRADES = [100.0, -50.0, 200.0, -50.0, -50.0, 300.0]  # W L W L L W


def test_trade_stats_hand_computed():
    s = trade_stats(TRADES)
    assert s["n_trades"] == 6
    assert s["net_profit"] == pytest.approx(450.0)
    assert s["gross_profit"] == pytest.approx(600.0)
    assert s["gross_loss"] == pytest.approx(150.0)
    assert s["profit_factor"] == pytest.approx(4.0)
    assert s["win_rate"] == pytest.approx(0.5)
    assert s["avg_win"] == pytest.approx(200.0)
    assert s["avg_loss"] == pytest.approx(-50.0)
    assert s["expectancy"] == pytest.approx(75.0)
    assert s["max_consecutive_wins"] == 1
    assert s["max_consecutive_losses"] == 2


def test_trade_stats_empty():
    s = trade_stats([])
    assert s["n_trades"] == 0
    assert s["profit_factor"] is None
    assert s["win_rate"] is None


def test_trade_stats_no_losses_profit_factor_is_none_not_inf():
    s = trade_stats([10.0, 20.0])
    assert s["profit_factor"] is None


def test_daily_stats_hand_computed():
    s = daily_stats(pd.Series([100.0, -50.0, 0.0, 200.0, -100.0]))
    assert s["n_days"] == 5
    assert s["mean"] == pytest.approx(30.0)
    assert s["median"] == pytest.approx(0.0)
    assert s["best_day"] == pytest.approx(200.0)
    assert s["worst_day"] == pytest.approx(-100.0)
    assert s["pct_profitable_days"] == pytest.approx(0.4)
    assert s["pct_losing_days"] == pytest.approx(0.4)


def test_sharpe_matches_manual_computation():
    rng = np.random.default_rng(7)
    r = pd.Series(rng.normal(0.0002, 0.01, 500))
    expected = r.mean() / r.std(ddof=1) * np.sqrt(252)
    assert sharpe_ratio(r) == pytest.approx(float(expected))


def test_sharpe_zero_vol_is_zero_not_inf():
    assert sharpe_ratio(pd.Series([0.01] * 100)) == 0.0


def test_sortino_uses_downside_only():
    r = pd.Series([0.02, -0.01, 0.03, -0.02, 0.01])
    downside = r[r < 0]
    dd = np.sqrt((downside**2).mean())
    expected = r.mean() / dd * np.sqrt(252)
    assert sortino_ratio(r) == pytest.approx(float(expected))


def test_max_drawdown_hand_computed():
    dd = max_drawdown(pd.Series([100.0, 120.0, 90.0, 130.0, 110.0]))
    assert dd["max_drawdown_abs"] == pytest.approx(30.0)
    assert dd["max_drawdown_pct"] == pytest.approx(0.25)


def test_equity_curve():
    eq = equity_curve(pd.Series([10.0, -5.0, 20.0]), starting_equity=1000.0)
    assert list(eq) == [1010.0, 1005.0, 1025.0]


def test_summarize_smoke():
    daily = pd.Series([100.0, -50.0, 30.0, -20.0, 60.0])
    s = summarize(TRADES, daily, starting_equity=10_000.0)
    assert s["trade_n_trades"] == 6
    assert s["daily_n_days"] == 5
    assert s["final_equity"] == pytest.approx(10_120.0)
    assert "sharpe" in s and "sortino" in s and "max_drawdown_pct" in s
