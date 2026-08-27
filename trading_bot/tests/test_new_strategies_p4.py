"""Pass-4 exploratory strategies: vol breakout, funding carry, spread
instrument — directional sanity, timestamp safety, validation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.core.types import Side, Venue
from trading_bot.data_pipeline.spread import (
    build_spread_frame,
    net_funding,
    spread_market_spec,
)
from trading_bot.strategies.funding_carry import FundingCarry
from trading_bot.strategies.vol_breakout import VolatilityBreakout
from trading_bot.tests.conftest import make_bars

SMALL = {"vol_window": 5, "rank_window": 10, "squeeze_pctile": 0.6,
         "break_window": 5, "hold_bars": 3}


def run_over(strategy, bars):
    strategy.reset()
    return [strategy.on_bar(b) for b in bars]


# ---- volatility breakout --------------------------------------------------------
def test_vol_breakout_fires_on_squeeze_break_and_time_exits():
    # A shrinking oscillation: volatility decays (true squeeze, latest vol
    # ranks lowest) while price stays strictly INSIDE its prior range, so no
    # breakout can fire before the engineered one. Fully deterministic.
    amps = np.linspace(0.5, 0.01, 40)
    quiet = [100.0 + ((-1) ** i) * a for i, a in enumerate(amps)]
    closes = quiet + [quiet[-1] + 2.0]                          # hard break upward
    closes += [closes[-1]] * 5                                  # quiet aftermath
    bars = make_bars(closes)
    strat = VolatilityBreakout(SMALL)
    signals = run_over(strat, bars)
    breaks = [s for s in signals if s is not None and s.direction is Side.LONG]
    assert breaks, "squeeze breakout must fire on the expansion bar"
    first = signals.index(breaks[0])
    assert first == 40                                          # the break bar itself
    # Time exit exactly hold_bars later:
    assert signals[first + SMALL["hold_bars"]].direction is Side.FLAT


def test_vol_breakout_silent_without_squeeze():
    rng = np.random.default_rng(5)
    noisy = list(100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, 60))))  # always volatile
    strat = VolatilityBreakout({**SMALL, "squeeze_pctile": 0.05})
    signals = [s for s in run_over(strat, make_bars(noisy))
               if s is not None and s.direction is not Side.FLAT]
    assert signals == []                                        # never armed


def test_vol_breakout_validation_and_warmup():
    with pytest.raises(ValueError):
        VolatilityBreakout({**SMALL, "squeeze_pctile": 1.5})
    strat = VolatilityBreakout(SMALL)
    assert strat.warmup_bars == SMALL["vol_window"] + SMALL["rank_window"]


# ---- funding carry --------------------------------------------------------------
def make_funding(values):
    idx = pd.date_range("2026-01-01", periods=len(values), freq="1h", tz="UTC")
    return pd.Series(values, index=idx, name="funding_rate")


def hourly_bars(n, start="2026-01-01"):
    return make_bars([100.0] * n, start=pd.Timestamp(start, tz="UTC"), freq_minutes=60)


FC_PARAMS = {"lookback_hours": 6, "rank_window_hours": 96,
             "entry_pctile": 0.8, "neutral_band": 0.1}


def test_funding_carry_shorts_crowded_longs_and_vice_versa():
    values = [0.0] * 150 + [0.001] * 30 + [0.0] * 40 + [-0.001] * 30
    funding = make_funding(values)
    bars = hourly_bars(len(values))
    strat = FundingCarry(FC_PARAMS, funding=funding)
    signals = run_over(strat, bars)

    hot = [s for s in signals[150:180] if s is not None]
    assert hot and all(s.direction is Side.SHORT for s in hot)
    cold = [s for s in signals[220:] if s is not None]
    assert any(s.direction is Side.LONG for s in cold)


def test_funding_carry_silent_until_history_exists():
    funding = make_funding([0.0001] * 300)
    bars = hourly_bars(300)
    strat = FundingCarry(FC_PARAMS, funding=funding)
    signals = run_over(strat, bars)
    assert all(s is None for s in signals[:FC_PARAMS["rank_window_hours"] - 2])


def test_funding_carry_truncation_invariance():
    rng = np.random.default_rng(9)
    funding = make_funding(list(rng.normal(0, 5e-4, 400)))
    bars = hourly_bars(400)
    full = run_over(FundingCarry(FC_PARAMS, funding=funding), bars)
    for k in (150, 250, 399):
        truncated = run_over(FundingCarry(FC_PARAMS, funding=funding), bars[:k])
        assert truncated == full[:k]


def test_funding_carry_validation():
    with pytest.raises(ValueError, match="entry_pctile"):
        FundingCarry({**FC_PARAMS, "entry_pctile": 0.4}, funding=make_funding([0.0] * 10))
    naive = pd.Series([0.0], index=pd.DatetimeIndex(["2026-01-01"]))
    with pytest.raises(ValueError, match="tz-aware"):
        FundingCarry(FC_PARAMS, funding=naive)


# ---- spread instrument ----------------------------------------------------------
def leg(closes, start="2026-01-01"):
    from trading_bot.data_pipeline.frames import bars_to_frame
    return bars_to_frame(make_bars(closes, start=pd.Timestamp(start, tz="UTC"),
                                   freq_minutes=60))


def test_spread_frame_construction():
    eth = leg([2000.0, 2100.0, 2050.0] * 5)
    btc = leg([70000.0, 70000.0, 70000.0] * 5)
    s = build_spread_frame(eth, btc, scale=100_000.0)
    assert len(s) == 15
    assert s["close"].iloc[0] == pytest.approx(100_000 * 2000 / 70000)
    # H is the extremes-coincide BOUND: high_num / low_den * scale (or O/C)
    assert (s["high"] >= s[["open", "close"]].max(axis=1) - 1e-9).all()
    assert (s["low"] <= s[["open", "close"]].min(axis=1) + 1e-9).all()


def test_spread_alignment_is_inner_join():
    eth = leg([2000.0] * 20)
    btc = leg([70000.0] * 15)
    s = build_spread_frame(eth, btc)
    assert len(s) == 15
    with pytest.raises(ValueError, match="fewer than 10"):
        build_spread_frame(leg([2000.0] * 5), leg([70000.0] * 5))


def test_spread_spec_has_two_leg_costs():
    spec = spread_market_spec()
    assert spec.fees.taker == pytest.approx(0.0009)   # 2 x 4.5 bps
    assert spec.fees.maker == pytest.approx(0.0003)   # 2 x 1.5 bps
    assert spec.venue is Venue.SYNTHETIC              # no executor can trade it
    assert spec.has_funding


def test_net_funding_difference():
    fa = make_funding([0.0005] * 10)
    fb = make_funding([0.0001] * 10)
    net = net_funding(fa, fb)
    assert (net == pytest.approx(0.0004)).all() or np.allclose(net, 0.0004)


def test_spread_runs_through_the_engine():
    from trading_bot.backtesting.engine import BacktestConfig, BacktestEngine
    from trading_bot.data_pipeline.frames import frame_to_bars
    from trading_bot.strategies.mean_reversion import ZScoreMeanReversion
    from trading_bot.tests.test_engine import loose_limits

    rng = np.random.default_rng(11)
    eth = leg(list(2000 * np.exp(np.cumsum(rng.normal(0, 0.004, 300)))))
    btc = leg(list(70000 * np.exp(np.cumsum(rng.normal(0, 0.003, 300)))))
    spec = spread_market_spec()
    frame = build_spread_frame(eth, btc)
    bars = frame_to_bars(frame, spec.market_id)
    result = BacktestEngine(spec, ZScoreMeanReversion({"window": 30}),
                            loose_limits(), BacktestConfig()).run(bars)
    assert result.n_bars == 300                       # machinery accepts the instrument


# ---- walk-forward factory hook --------------------------------------------------
def test_walkforward_strategy_factory_equivalent():
    from trading_bot.backtesting.engine import BacktestConfig
    from trading_bot.core.market import get_market
    from trading_bot.research.experiments import generate_synthetic_bars
    from trading_bot.research.walkforward import run_walkforward
    from trading_bot.strategies.momentum import SimpleMomentum
    from trading_bot.tests.test_engine import loose_limits

    bars = generate_synthetic_bars(n=400, seed=3, market_id="SYNTH")
    common = dict(spec=get_market("SYNTH"), grid=[{"lookback": 5}, {"lookback": 20}],
                  bars=bars, limits=loose_limits(),
                  bt_config=BacktestConfig(initial_equity=50_000),
                  train_bars=150, test_bars=80)
    by_name = run_walkforward(strategy_name="simple_momentum", **common)
    by_factory = run_walkforward(strategy_name="simple_momentum",
                                 strategy_factory=lambda p: SimpleMomentum(p), **common)
    assert by_name.chosen_params_history == by_factory.chosen_params_history
    assert by_name.oos_metrics["trade_net_profit"] == pytest.approx(
        by_factory.oos_metrics["trade_net_profit"])
