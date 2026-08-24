"""Strategy abstraction and the SimpleMomentum baseline: warmup respected,
signals deterministic, and — critically — unaffected by removing the future."""

from __future__ import annotations

import pytest

from trading_bot.core.types import Side
from trading_bot.research.experiments import generate_synthetic_bars
from trading_bot.strategies.momentum import SimpleMomentum
from trading_bot.tests.conftest import make_bars


def run_over(strategy, bars):
    strategy.reset()
    return [strategy.on_bar(b) for b in bars]


def test_no_signal_during_warmup():
    strat = SimpleMomentum({"lookback": 3})
    bars = make_bars([100, 101, 102, 103, 104, 105])
    signals = run_over(strat, bars)
    assert signals[: strat.warmup_bars - 1] == [None] * (strat.warmup_bars - 1)
    assert signals[strat.warmup_bars - 1] is not None


def test_rising_prices_long_falling_prices_short():
    strat = SimpleMomentum({"lookback": 3})
    up = run_over(strat, make_bars([100, 101, 102, 103, 104, 105]))
    assert all(s.direction is Side.LONG for s in up if s is not None)
    down = run_over(strat, make_bars([105, 104, 103, 102, 101, 100]))
    assert all(s.direction is Side.SHORT for s in down if s is not None)


def test_threshold_produces_flat():
    strat = SimpleMomentum({"lookback": 3, "threshold": 0.5})  # 50% move required
    signals = run_over(strat, make_bars([100, 100.1, 100.2, 100.1, 100.3]))
    assert all(s.direction is Side.FLAT for s in signals if s is not None)


def test_signal_timestamp_equals_bar_close_time():
    strat = SimpleMomentum({"lookback": 3})
    bars = make_bars([100, 101, 102, 103, 104])
    for bar, sig in zip(bars, run_over(strat, bars)):
        if sig is not None:
            assert sig.ts == bar.ts


def test_truncating_the_future_never_changes_past_signals():
    """The strategy-level look-ahead test: signals over bars[:k] must be
    identical to the first k signals over the full series, for any k."""
    bars = generate_synthetic_bars(n=120, seed=9)
    strat = SimpleMomentum({"lookback": 10})
    full = run_over(strat, bars)
    for k in (30, 60, 90, 119):
        truncated = run_over(SimpleMomentum({"lookback": 10}), bars[:k])
        assert truncated == full[:k]


def test_determinism():
    bars = generate_synthetic_bars(n=100, seed=5)
    a = run_over(SimpleMomentum(), bars)
    b = run_over(SimpleMomentum(), bars)
    assert a == b


def test_unknown_param_rejected():
    with pytest.raises(ValueError, match="unknown params"):
        SimpleMomentum({"lookbak": 20})  # typo must fail loudly, not be ignored


def test_describe():
    d = SimpleMomentum({"lookback": 5}).describe()
    assert d["name"] == "simple_momentum"
    assert d["params"]["lookback"] == 5
    assert d["warmup_bars"] == 6
