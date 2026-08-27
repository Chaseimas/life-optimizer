"""Random-entry beta control (repo-grade): mechanics and determinism."""

from __future__ import annotations

import pytest

from trading_bot.backtesting.engine import BacktestConfig, BacktestEngine
from trading_bot.core.market import get_market
from trading_bot.core.types import Side
from trading_bot.research.controls import RandomTimedEntries, run_random_entry_control
from trading_bot.research.experiments import generate_synthetic_bars
from trading_bot.strategies.momentum import SimpleMomentum
from trading_bot.tests.test_engine import loose_limits

SYNTH = get_market("SYNTH")


def test_random_timed_entries_schedule():
    bars = generate_synthetic_bars(n=20, seed=1, market_id="SYNTH")
    strat = RandomTimedEntries({5: (Side.LONG, 3)})
    signals = [strat.on_bar(b) for b in bars]
    assert signals[5] is not None and signals[5].direction is Side.LONG
    assert signals[8] is not None and signals[8].direction is Side.FLAT
    assert all(s is None for i, s in enumerate(signals) if i not in (5, 8))


@pytest.fixture(scope="module")
def actual_run():
    bars = generate_synthetic_bars(n=300, seed=23, market_id="SYNTH")
    cfg = BacktestConfig(initial_equity=50_000, stop_atr_mult=2.0, atr_period=14)
    result = BacktestEngine(SYNTH, SimpleMomentum({"lookback": 5}),
                            loose_limits(), cfg).run(bars)
    return bars, cfg, result


def test_control_shape_and_determinism(actual_run):
    bars, cfg, result = actual_run
    kwargs = dict(spec=SYNTH, bars=bars, trades=result.trades, bt_config=cfg,
                  limits=loose_limits(), n_replicates=10, seed=42)
    a = run_random_entry_control(**kwargs)
    b = run_random_entry_control(**kwargs)
    assert a == b                                     # same seed -> same null
    assert a.n_replicates == 10
    assert 0.0 <= a.actual_percentile <= 1.0
    assert a.null_p5 <= a.null_p50 <= a.null_p95
    assert a.n_profile_trades == len(result.trades)


def test_control_direction_filter(actual_run):
    bars, cfg, result = actual_run
    longs_only = run_random_entry_control(
        spec=SYNTH, bars=bars, trades=result.trades, bt_config=cfg,
        limits=loose_limits(), directions=(Side.LONG,), n_replicates=5, seed=1)
    n_longs = sum(1 for t in result.trades if t.direction is Side.LONG)
    expected_net = sum(t.net_pnl for t in result.trades if t.direction is Side.LONG)
    assert longs_only.n_profile_trades == n_longs
    assert longs_only.actual_net == pytest.approx(expected_net)


def test_control_requires_matching_trades(actual_run):
    bars, cfg, result = actual_run
    only_shorts = [t for t in result.trades if t.direction is Side.SHORT]
    if not only_shorts:  # ensure the error path is exercised regardless
        with pytest.raises(ValueError, match="no trades"):
            run_random_entry_control(
                spec=SYNTH, bars=bars, trades=[], bt_config=cfg,
                limits=loose_limits(), n_replicates=2)
    else:
        with pytest.raises(ValueError, match="no trades"):
            run_random_entry_control(
                spec=SYNTH, bars=bars, trades=only_shorts, bt_config=cfg,
                limits=loose_limits(), directions=(Side.LONG,), n_replicates=2)
