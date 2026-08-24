"""Event-driven backtester: hand-computed scenarios, conservative fills,
risk integration, and truncation invariance (the engine-level no-lookahead
guarantee)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from trading_bot.backtesting.engine import BacktestConfig, BacktestEngine
from trading_bot.core.config import RiskLimits
from trading_bot.core.events import Bar, Signal
from trading_bot.core.market import get_market
from trading_bot.core.types import Side
from trading_bot.research.experiments import generate_synthetic_bars
from trading_bot.strategies.base_strategy import BaseStrategy
from trading_bot.strategies.momentum import SimpleMomentum

MNQ = get_market("MNQ")
BTC = get_market("HL:BTC")
SYNTH = get_market("SYNTH")

T0 = datetime(2026, 1, 5, 23, 40, tzinfo=timezone.utc)


def loose_limits(**over) -> RiskLimits:
    base = dict(
        max_daily_loss=1e9, max_risk_per_trade=0.005, max_position_size=1e6,
        max_trades_per_day=10_000, max_drawdown=0.99, max_open_exposure=1e12,
        max_consecutive_losses=10_000,
    )
    base.update(over)
    return RiskLimits(**base)


class Scripted(BaseStrategy):
    """Emits pre-scripted signals at given bar indexes (test instrument)."""

    name = "scripted"

    def __init__(self, script: dict[int, Side]):
        super().__init__({})
        self.script = script
        self.i = -1

    @property
    def warmup_bars(self) -> int:
        return 0

    def on_bar(self, bar: Bar) -> Signal | None:
        self.i += 1
        if self.i in self.script:
            return Signal(ts=bar.ts, market_id=bar.market_id,
                          direction=self.script[self.i], reason=f"scripted@{self.i}")
        return None

    def reset(self) -> None:
        self.i = -1


def bar(i: int, o: float, h: float, lo: float, c: float, market="MNQ", v=1000.0,
        base: datetime = T0) -> Bar:
    return Bar(ts=base + timedelta(minutes=5 * (i + 1)), market_id=market,
               open=o, high=h, low=lo, close=c, volume=v)


# A base far from UTC midnight, for tests where the whole scenario must stay
# within ONE trading day (daily halts reset at the UTC date boundary).
MIDDAY = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)


# ---- scenario A: long entry, stop-loss exit, exact arithmetic -------------------
def scenario_a_result(**cfg_over):
    bars = [
        bar(0, 20000, 20005, 19995, 20000),   # signal LONG at close
        bar(1, 20000, 20010, 19990, 20005),   # entry at open: 20000 + 1 tick
        bar(2, 19985, 19995, 19970, 19980),   # low 19970 <= stop 19975.25 -> stopped
        bar(3, 19980, 19985, 19975.5, 19980),
    ]
    cfg = BacktestConfig(initial_equity=100_000, fixed_stop_points=25.0,
                         stop_atr_mult=None, **cfg_over)
    engine = BacktestEngine(MNQ, Scripted({0: Side.LONG}), loose_limits(), cfg)
    return engine.run(bars), bars


def test_stop_loss_hand_computed():
    result, bars = scenario_a_result()
    assert len(result.trades) == 1
    t = result.trades[0]
    # Entry: next bar's open + 1 tick slippage. Size: $500 risk / (25pt * $2) = 10.
    assert t.entry_ts == bars[1].ts
    assert t.entry_price == pytest.approx(20000.25)
    assert t.size == 10
    assert t.stop_price == pytest.approx(19975.25)
    # Exit: stop price - 1 tick sell slippage.
    assert t.exit_ts == bars[2].ts
    assert t.exit_price == pytest.approx(19975.00)
    assert t.exit_reason == "stop_loss"
    assert t.gross_pnl == pytest.approx((19975.00 - 20000.25) * 2 * 10)  # -505.0
    assert t.fees == pytest.approx(2 * 10 * 1.24)                        # 24.8
    assert t.net_pnl == pytest.approx(-529.8)
    assert t.slippage_cost == pytest.approx(0.25 * 2 * 10 * 2)           # both sides
    assert t.bars_held == 1
    assert result.metrics["final_equity"] == pytest.approx(100_000 - 529.8)
    assert result.metrics["trade_n_trades"] == 1


def test_take_profit_hand_computed():
    bars = [
        bar(0, 20000, 20005, 19995, 20000),
        bar(1, 20000, 20010, 19990, 20005),   # entry 20000.25, tp 20020.25
        bar(2, 20005, 20025, 20000, 20010),   # high 20025 >= tp -> take profit
    ]
    cfg = BacktestConfig(initial_equity=100_000, fixed_stop_points=25.0,
                         fixed_tp_points=20.0, stop_atr_mult=None)
    result = BacktestEngine(MNQ, Scripted({0: Side.LONG}), loose_limits(), cfg).run(bars)
    t = result.trades[0]
    assert t.exit_reason == "take_profit"
    assert t.tp_price == pytest.approx(20020.25)
    assert t.exit_price == pytest.approx(20020.00)   # tp - 1 tick sell slippage
    assert t.net_pnl == pytest.approx((20020.00 - 20000.25) * 2 * 10 - 24.8)  # 370.2


def test_gap_through_stop_fills_at_open_not_at_stop():
    bars = [
        bar(0, 20000, 20005, 19995, 20000),
        bar(1, 20000, 20010, 19990, 20005),           # entry 20000.25, stop 19975.25
        bar(2, 19950, 19960, 19940, 19955),           # gaps BELOW the stop
    ]
    cfg = BacktestConfig(initial_equity=100_000, fixed_stop_points=25.0, stop_atr_mult=None)
    result = BacktestEngine(MNQ, Scripted({0: Side.LONG}), loose_limits(), cfg).run(bars)
    t = result.trades[0]
    assert t.exit_reason == "stop_loss"
    # Filled at the (worse) open minus slippage — never at the stop price.
    assert t.exit_price == pytest.approx(19950 - 0.25)


def test_signal_flip_closes_and_reverses():
    bars = [
        bar(0, 20000, 20005, 19995, 20000),           # LONG signal
        bar(1, 20000, 20010, 19995, 20005),           # entry long 20000.25
        bar(2, 20010, 20015, 20005, 20010),           # SHORT signal at close
        bar(3, 20020, 20025, 20015, 20020),           # close long & enter short at open
        bar(4, 20020, 20025, 20015, 20018),
    ]
    cfg = BacktestConfig(initial_equity=100_000, fixed_stop_points=25.0, stop_atr_mult=None)
    result = BacktestEngine(
        MNQ, Scripted({0: Side.LONG, 2: Side.SHORT}), loose_limits(), cfg
    ).run(bars)
    assert len(result.trades) == 2
    first, second = result.trades
    assert first.direction is Side.LONG
    assert first.exit_reason == "signal_flip"
    assert first.exit_ts == bars[3].ts
    assert first.exit_price == pytest.approx(20019.75)  # sell at open - 1 tick
    assert first.net_pnl == pytest.approx((20019.75 - 20000.25) * 2 * 10 - 24.8)  # 365.2
    assert second.direction is Side.SHORT
    assert second.entry_ts == bars[3].ts
    assert second.entry_price == pytest.approx(20019.75)
    assert second.exit_reason == "end_of_data"
    # Second entry re-sized on updated equity: $100,365.2 * 0.5% / $50 -> 10.
    assert second.size == 10


def test_flat_signal_closes_position():
    bars = [
        bar(0, 20000, 20005, 19995, 20000),
        bar(1, 20000, 20010, 19995, 20005),
        bar(2, 20010, 20015, 20005, 20010),           # FLAT signal
        bar(3, 20012, 20015, 20008, 20010),
    ]
    cfg = BacktestConfig(initial_equity=100_000, fixed_stop_points=25.0, stop_atr_mult=None)
    result = BacktestEngine(
        MNQ, Scripted({0: Side.LONG, 2: Side.FLAT}), loose_limits(), cfg
    ).run(bars)
    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "signal_flat"
    assert result.trades[0].exit_ts == bars[3].ts


def test_daily_loss_halt_blocks_reentry_until_next_day():
    next_day = MIDDAY + timedelta(days=1)
    day2 = [
        bar(0, 19985, 19995, 19980, 19990, base=next_day),   # day-2 entry bar
        bar(1, 19990, 20000, 19985, 19995, base=next_day),
    ]
    bars = [
        bar(0, 20000, 20005, 19995, 20000, base=MIDDAY),     # LONG signal (day 1)
        bar(1, 20000, 20010, 19990, 20005, base=MIDDAY),     # entry
        bar(2, 19985, 19995, 19970, 19980, base=MIDDAY),     # stop-out -529.8 -> daily halt; LONG again
        bar(3, 19980, 19985, 19975.5, 19980, base=MIDDAY),   # re-entry DENIED (same day)
        bar(4, 19980, 19990, 19975.5, 19985, base=MIDDAY),   # LONG signal, executes next day
    ] + day2
    limits = loose_limits(max_daily_loss=300.0)
    cfg = BacktestConfig(initial_equity=100_000, fixed_stop_points=25.0, stop_atr_mult=None)
    result = BacktestEngine(
        MNQ, Scripted({0: Side.LONG, 2: Side.LONG, 4: Side.LONG}), limits, cfg
    ).run(bars)
    # Trade 1: the stop-out. The bars[2] signal is denied at bars[3]'s open
    # (same day, halted). The bars[4] signal executes on day 2 (halt lifted).
    assert len(result.trades) == 2
    assert result.trades[0].exit_reason == "stop_loss"
    assert result.trades[1].entry_ts == day2[0].ts


def test_consecutive_loss_halt():
    limits = loose_limits(max_consecutive_losses=2)
    # Two scripted losing longs, then a third signal the same day -> denied.
    bars = [
        bar(0, 20000, 20005, 19995, 20000, base=MIDDAY),   # LONG
        bar(1, 20000, 20010, 19990, 20005, base=MIDDAY),   # entry 1
        bar(2, 19985, 19995, 19970, 19980, base=MIDDAY),   # stop 1; LONG again
        bar(3, 19990, 20000, 19985, 19995, base=MIDDAY),   # entry 2
        bar(4, 19975, 19980, 19960, 19970, base=MIDDAY),   # stop 2 -> streak 2 -> halt; LONG
        bar(5, 19975, 19985, 19970, 19980, base=MIDDAY),   # entry denied
        bar(6, 19980, 19990, 19975.5, 19985, base=MIDDAY),
    ]
    cfg = BacktestConfig(initial_equity=100_000, fixed_stop_points=25.0, stop_atr_mult=None)
    result = BacktestEngine(
        MNQ, Scripted({0: Side.LONG, 2: Side.LONG, 4: Side.LONG}), limits, cfg
    ).run(bars)
    assert len(result.trades) == 2
    assert all(t.exit_reason == "stop_loss" for t in result.trades)


def test_max_drawdown_trips_kill_switch_and_stops_run():
    limits = loose_limits(max_drawdown=0.004)  # 0.4%: one stop-out (~0.53%) trips it
    bars = [
        bar(0, 20000, 20005, 19995, 20000),
        bar(1, 20000, 20010, 19990, 20005),
        bar(2, 19985, 19995, 19970, 19980),           # stop-out -> drawdown > 0.4%
        bar(3, 19980, 19985, 19975.5, 19980),         # LONG signal -> must be ignored
        bar(4, 19985, 19995, 19980, 19990),
    ]
    cfg = BacktestConfig(initial_equity=100_000, fixed_stop_points=25.0, stop_atr_mult=None)
    result = BacktestEngine(
        MNQ, Scripted({0: Side.LONG, 3: Side.LONG}), limits, cfg
    ).run(bars)
    assert len(result.trades) == 1
    assert any("KILL SWITCH" in h for h in result.halts)


def test_funding_charged_to_longs():
    import pandas as pd

    bars = [
        bar(0, 60000, 60010, 59990, 60000, market="HL:BTC"),
        bar(1, 60000, 60010, 59990, 60000, market="HL:BTC"),   # entry
        bar(2, 60000, 60010, 59990, 60000, market="HL:BTC"),   # funding event inside
        bar(3, 60000, 60010, 59990, 60000, market="HL:BTC"),   # force close at end
    ]
    funding = pd.Series(
        [0.0001],
        index=pd.DatetimeIndex([bars[2].ts - timedelta(seconds=1)], tz="UTC"),
    )
    cfg = BacktestConfig(initial_equity=100_000, fixed_stop_points=5000.0, stop_atr_mult=None)
    result = BacktestEngine(
        BTC, Scripted({0: Side.LONG}), loose_limits(), cfg, funding=funding
    ).run(bars)
    t = result.trades[0]
    assert t.size == pytest.approx(0.1)               # $500 risk / $5000 stop
    assert t.entry_price == pytest.approx(60006.0)    # 1bp slippage, tick 1.0
    # Funding: 0.0001 * (60000 * 0.1) = $0.60 paid by the long.
    assert t.funding == pytest.approx(0.6)
    fees = 0.00045 * (60006.0 * 0.1) + 0.00045 * (59994.0 * 0.1)
    assert t.net_pnl == pytest.approx((59994.0 - 60006.0) * 0.1 - fees - 0.6)


def test_truncating_future_bars_never_changes_closed_trades():
    bars = generate_synthetic_bars(n=300, seed=7, market_id="SYNTH")
    cfg = BacktestConfig(initial_equity=50_000, stop_atr_mult=2.0, atr_period=14)

    def run(bs):
        return BacktestEngine(
            SYNTH, SimpleMomentum({"lookback": 5}), loose_limits(), cfg
        ).run(bs)

    full = run(bars)
    cutoff = bars[199].ts
    truncated = run(bars[:200])

    def closed_before(result):
        return [
            (t.entry_ts, t.exit_ts, t.direction, round(t.net_pnl, 10))
            for t in result.trades
            if t.exit_ts <= cutoff and t.exit_reason != "end_of_data"
        ]

    assert closed_before(full) == closed_before(truncated)
    assert len(closed_before(full)) > 0  # the check must actually check something


def test_engine_rejects_bad_input():
    cfg = BacktestConfig()
    engine = BacktestEngine(MNQ, Scripted({}), loose_limits(), cfg)
    with pytest.raises(ValueError, match="no bars"):
        engine.run([])
    b0 = bar(0, 20000, 20005, 19995, 20000)
    b1 = bar(1, 20000, 20005, 19995, 20000)
    with pytest.raises(ValueError, match="strictly increasing"):
        engine.run([b1, b0])
    foreign = bar(2, 1, 2, 0.5, 1, market="HL:BTC")
    with pytest.raises(ValueError, match="one market"):
        engine.run([b0, foreign])


def test_no_stop_resolvable_means_no_trade():
    # No signal stop, no fixed stop, ATR not warmed up -> refuse to trade.
    bars = [
        bar(0, 20000, 20005, 19995, 20000),
        bar(1, 20000, 20010, 19990, 20005),
        bar(2, 20005, 20010, 20000, 20008),
    ]
    cfg = BacktestConfig(initial_equity=100_000, stop_atr_mult=2.0, atr_period=14)
    result = BacktestEngine(MNQ, Scripted({0: Side.LONG}), loose_limits(), cfg).run(bars)
    assert len(result.trades) == 0
