"""Phase 7 baseline strategies: directional sanity on crafted series, warmup
discipline, and truncation invariance (the strategy-level leak test) for
EVERY registered strategy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from trading_bot.core.events import Bar
from trading_bot.core.types import Side
from trading_bot.research.experiments import generate_synthetic_bars
from trading_bot.strategies.breakout import OpeningRangeBreakout
from trading_bot.strategies.mean_reversion import ZScoreMeanReversion
from trading_bot.strategies.regime import EfficiencyRatioTracker, RegimeGatedMomentum
from trading_bot.strategies.registry import STRATEGY_REGISTRY, make_strategy
from trading_bot.strategies.vwap import RollingVWAPStrategy
from trading_bot.tests.conftest import make_bars


def run_over(strategy, bars):
    strategy.reset()
    return [strategy.on_bar(b) for b in bars]


# ---- registry -------------------------------------------------------------------
def test_registry_contains_all_phase7_strategies():
    for name in ("simple_momentum", "zscore_mean_reversion", "rolling_vwap",
                 "opening_range_breakout", "regime_gated_momentum"):
        assert name in STRATEGY_REGISTRY
        s = make_strategy(name)
        assert s.name == name


def test_registry_unknown_strategy():
    with pytest.raises(KeyError, match="Unknown strategy"):
        make_strategy("holy_grail")


@pytest.mark.parametrize("name", sorted(STRATEGY_REGISTRY))
def test_every_strategy_is_truncation_invariant(name):
    """Removing future bars must never change past signals — for every
    registered strategy, not just the ones we remembered to test."""
    bars = generate_synthetic_bars(n=250, seed=13, market_id="SYNTH")
    full = run_over(make_strategy(name), bars)
    for k in (100, 180, 249):
        truncated = run_over(make_strategy(name), bars[:k])
        assert truncated == full[:k], f"{name} changed the past when the future was removed"


@pytest.mark.parametrize("name", sorted(STRATEGY_REGISTRY))
def test_every_strategy_respects_warmup(name):
    bars = generate_synthetic_bars(n=250, seed=13, market_id="SYNTH")
    strategy = make_strategy(name)
    signals = run_over(strategy, bars)
    warm = strategy.warmup_bars
    assert all(s is None for s in signals[: warm - 1])


# ---- mean reversion -------------------------------------------------------------
def test_mean_reversion_fades_a_spike():
    closes = [100.0] * 19 + [130.0]           # huge upside extension
    signals = run_over(ZScoreMeanReversion({"window": 20}), make_bars(closes))
    assert signals[-1] is not None
    assert signals[-1].direction is Side.SHORT

    closes = [100.0] * 19 + [70.0]            # downside extension
    signals = run_over(ZScoreMeanReversion({"window": 20}), make_bars(closes))
    assert signals[-1].direction is Side.LONG


def test_mean_reversion_flattens_after_reversion():
    closes = [100.0] * 19 + [130.0] + [100.5] * 15
    signals = run_over(ZScoreMeanReversion({"window": 20}), make_bars(closes))
    assert signals[19].direction is Side.SHORT
    # Once the spike leaves the window, price sits at the mean -> FLAT.
    flat_signals = [s for s in signals[20:] if s is not None]
    assert any(s.direction is Side.FLAT for s in flat_signals)


def test_mean_reversion_param_validation():
    with pytest.raises(ValueError, match="entry_z"):
        ZScoreMeanReversion({"entry_z": 1.0, "exit_z": 2.0})
    with pytest.raises(ValueError, match="window"):
        ZScoreMeanReversion({"window": 3})


# ---- vwap -----------------------------------------------------------------------
def test_vwap_fade_shorts_extension_above():
    closes = [100.0] * 29 + [103.0]           # 3% above the rolling VWAP
    strat = RollingVWAPStrategy({"window": 20, "entry_dist": 0.005})
    signals = run_over(strat, make_bars(closes))
    assert signals[-1] is not None
    assert signals[-1].direction is Side.SHORT


def test_vwap_trend_goes_with_extension():
    closes = [100.0] * 29 + [103.0]
    strat = RollingVWAPStrategy({"window": 20, "mode": "trend", "entry_dist": 0.005})
    signals = run_over(strat, make_bars(closes))
    assert signals[-1].direction is Side.LONG


def test_vwap_flat_near_vwap():
    closes = [100.0] * 40                     # glued to VWAP
    strat = RollingVWAPStrategy({"window": 20})
    signals = [s for s in run_over(strat, make_bars(closes)) if s is not None]
    assert signals and all(s.direction is Side.FLAT for s in signals)


def test_vwap_param_validation():
    with pytest.raises(ValueError, match="mode"):
        RollingVWAPStrategy({"mode": "sideways"})
    with pytest.raises(ValueError, match="exit_dist"):
        RollingVWAPStrategy({"entry_dist": 0.001, "exit_dist": 0.005})


# ---- opening range breakout -----------------------------------------------------
def orb_bar(ts: datetime, o, h, lo, c) -> Bar:
    return Bar(ts=ts, market_id="SYNTH", open=o, high=h, low=lo, close=c, volume=100.0)


def test_orb_breaks_out_once_per_direction_and_day():
    day = datetime(2026, 3, 2, tzinfo=timezone.utc)
    strat = OpeningRangeBreakout({"range_minutes": 60, "flat_hour": 23})
    bars = []
    # Range hour: 00:05 .. 01:00, range [99, 101]
    for i in range(12):
        bars.append(orb_bar(day + timedelta(minutes=5 * (i + 1)), 100, 101, 99, 100))
    # Later: two consecutive breakout closes above 101.
    bars.append(orb_bar(day + timedelta(hours=2), 100, 103.5, 100, 103))
    bars.append(orb_bar(day + timedelta(hours=2, minutes=5), 103, 104, 102.5, 103.5))
    # End of day.
    bars.append(orb_bar(day + timedelta(hours=23, minutes=5), 103, 103.5, 102.5, 103))
    signals = run_over(strat, bars)
    assert all(s is None for s in signals[:12])          # range building: silent
    assert signals[12].direction is Side.LONG            # first breakout fires
    assert signals[13] is None                           # no re-entry same day
    assert signals[14].direction is Side.FLAT            # day exit

    # Next day: fresh range, breakout fires again.
    day2 = day + timedelta(days=1)
    bars2 = [orb_bar(day2 + timedelta(minutes=5 * (i + 1)), 100, 101, 99, 100) for i in range(12)]
    bars2.append(orb_bar(day2 + timedelta(hours=3), 100, 96.5, 95.5, 96))  # downside break
    signals2 = [strat.on_bar(b) for b in bars2]          # continue same instance
    assert signals2[-1].direction is Side.SHORT


def test_orb_no_signal_before_range_completes():
    day = datetime(2026, 3, 2, tzinfo=timezone.utc)
    strat = OpeningRangeBreakout({"range_minutes": 60})
    inside = [orb_bar(day + timedelta(minutes=5 * (i + 1)), 100, 105, 95, 104) for i in range(6)]
    assert all(s is None for s in run_over(strat, inside))


# ---- regime ---------------------------------------------------------------------
def test_efficiency_ratio_extremes():
    er = EfficiencyRatioTracker(10)
    out = [er.update(float(c)) for c in range(1, 13)]    # perfect trend
    assert out[-1] == pytest.approx(1.0)

    er.reset()
    zigzag = [100.0, 101.0] * 10                          # pure churn
    vals = [er.update(c) for c in zigzag]
    assert vals[-1] is not None and vals[-1] <= 0.15


def test_regime_gate_passes_trend_blocks_churn():
    strat = RegimeGatedMomentum({"lookback": 5, "er_window": 5, "er_min": 0.5})

    trend = make_bars([100 + i for i in range(30)])
    trend_signals = [s for s in run_over(strat, trend) if s is not None]
    assert trend_signals and all(s.direction is Side.LONG for s in trend_signals)
    assert "trending" in trend_signals[-1].reason

    churn = make_bars([100.0, 101.0] * 15)
    churn_signals = [s for s in run_over(strat, churn) if s is not None]
    assert churn_signals and all(s.direction is Side.FLAT for s in churn_signals)
    assert "churn" in churn_signals[-1].reason
