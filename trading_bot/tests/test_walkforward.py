"""Walk-forward: window mechanics, warmup gating, OOS aggregation honesty."""

from __future__ import annotations

import pandas as pd
import pytest

from trading_bot.backtesting.engine import BacktestConfig
from trading_bot.core.config import RiskLimits
from trading_bot.core.market import get_market
from trading_bot.core.types import Side
from trading_bot.research.experiments import generate_synthetic_bars
from trading_bot.research.walkforward import (
    _WarmupGate,
    expand_grid,
    format_walkforward_report,
    run_walkforward,
)
from trading_bot.strategies.momentum import SimpleMomentum

SYNTH = get_market("SYNTH")

LIMITS = RiskLimits(
    max_daily_loss=1e9, max_risk_per_trade=0.005, max_position_size=1e6,
    max_trades_per_day=10_000, max_drawdown=0.99, max_open_exposure=1e12,
    max_consecutive_losses=10_000,
)


def test_expand_grid():
    assert expand_grid({"a": [1, 2], "b": [3]}) == [{"a": 1, "b": 3}, {"a": 2, "b": 3}]
    assert expand_grid({}) == [{}]
    assert len(expand_grid({"a": [1, 2], "b": [3, 4], "c": [5]})) == 4


def test_warmup_gate_suppresses_early_signals():
    bars = generate_synthetic_bars(n=50, seed=1, market_id="SYNTH")
    live_from = bars[30].ts
    gate = _WarmupGate(SimpleMomentum({"lookback": 5}), live_from=live_from)
    signals = [gate.on_bar(b) for b in bars]
    for b, s in zip(bars[:30], signals[:30]):
        assert s is None, f"signal leaked during warmup at {b.ts}"
    # After live_from the inner strategy is warm and signals flow.
    assert any(s is not None for s in signals[30:])


@pytest.fixture(scope="module")
def wf_result():
    bars = generate_synthetic_bars(n=600, seed=3, market_id="SYNTH")
    return run_walkforward(
        spec=SYNTH,
        strategy_name="simple_momentum",
        grid=expand_grid({"lookback": [5, 20]}),
        bars=bars,
        limits=LIMITS,
        bt_config=BacktestConfig(initial_equity=50_000, stop_atr_mult=2.0, atr_period=14),
        train_bars=200,
        test_bars=100,
    ), bars


def test_window_layout(wf_result):
    result, bars = wf_result
    assert len(result.windows) == 4                      # starts at 0, 100, 200, 300
    assert result.n_experiments == 8                     # 4 windows x 2 params
    for w in result.windows:
        assert w.train_end < w.test_start                # train strictly before test
        assert w.chosen_params in result.grid
    # Test slices must not overlap.
    for a, b in zip(result.windows, result.windows[1:]):
        assert a.test_end <= b.test_start


def test_no_oos_trade_before_its_window(wf_result):
    result, _ = wf_result
    assert len(result.oos_trades) > 0
    first_test_start = result.windows[0].test_start
    for t in result.oos_trades:
        assert t.entry_ts >= first_test_start


def test_oos_aggregation(wf_result):
    result, _ = wf_result
    assert not result.oos_daily_pnl.index.has_duplicates
    m = result.oos_metrics
    assert m["trade_n_trades"] == len(result.oos_trades)
    for key in ("sharpe", "sortino", "max_drawdown_pct", "daily_mean"):
        assert key in m
    # Every window contributed its trade count.
    assert sum(w.n_test_trades for w in result.windows) == len(result.oos_trades)


def test_deterministic(wf_result):
    result, bars = wf_result
    rerun = run_walkforward(
        spec=SYNTH,
        strategy_name="simple_momentum",
        grid=expand_grid({"lookback": [5, 20]}),
        bars=bars,
        limits=LIMITS,
        bt_config=BacktestConfig(initial_equity=50_000, stop_atr_mult=2.0, atr_period=14),
        train_bars=200,
        test_bars=100,
    )
    assert rerun.chosen_params_history == result.chosen_params_history
    assert rerun.oos_metrics["trade_net_profit"] == pytest.approx(
        result.oos_metrics["trade_net_profit"]
    )


def test_report_renders(wf_result):
    result, _ = wf_result
    text = format_walkforward_report(result)
    assert "AGGREGATED OUT-OF-SAMPLE" in text
    assert "parameter stability" in text


def test_insufficient_data_rejected():
    bars = generate_synthetic_bars(n=100, seed=3, market_id="SYNTH")
    with pytest.raises(ValueError, match="not enough bars"):
        run_walkforward(
            spec=SYNTH, strategy_name="simple_momentum",
            grid=[{"lookback": 5}], bars=bars, limits=LIMITS,
            bt_config=BacktestConfig(), train_bars=200, test_bars=100,
        )
