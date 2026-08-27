"""Maker execution model: fill logic on OHLC, engine integration, honest
no-fill behavior, adverse-selection accounting, risk/kill-switch interaction,
and deterministic reproducibility."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from trading_bot.backtesting.engine import BacktestConfig, BacktestEngine
from trading_bot.backtesting.maker import (
    SCENARIOS,
    MakerParams,
    evaluate_fill,
    limit_price_for,
)
from trading_bot.core.events import Bar
from trading_bot.core.market import get_market
from trading_bot.core.types import Side
from trading_bot.risk.kill_switch import KillSwitch, KillSwitchReason
from trading_bot.tests.test_engine import Scripted, loose_limits

BTC = get_market("HL:BTC")
MIDDAY = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)


def bar(i, o, h, lo, c, v=1000.0) -> Bar:
    return Bar(ts=MIDDAY + timedelta(minutes=5 * (i + 1)), market_id="HL:BTC",
               open=o, high=h, low=lo, close=c, volume=v)


def rng():
    return np.random.default_rng(0)


# ---- pure fill logic ------------------------------------------------------------
def test_limit_price_placement():
    p0 = MakerParams(limit_offset_bps=0.0)
    assert limit_price_for(BTC, Side.LONG, 60000.0, p0) == 60000.0
    p10 = MakerParams(limit_offset_bps=10.0)
    assert limit_price_for(BTC, Side.LONG, 60000.0, p10) == 59940.0   # 10 bps below
    assert limit_price_for(BTC, Side.SHORT, 60000.0, p10) == 60060.0  # 10 bps above


def test_through_mode_fills_only_when_swept():
    p = MakerParams(fill_on="through", penetration_bps=1.0)  # pen = $6 at 60k
    # Swept: low trades > $6 below the limit.
    ev = evaluate_fill(bar(0, 60000, 60010, 59990, 60005), Side.LONG, 60000.0, p, rng())
    assert ev is not None and ev.fraction == 1.0 and ev.swept
    # Touched exactly but not swept: honest no-fill.
    assert evaluate_fill(bar(0, 60005, 60010, 60000, 60006), Side.LONG, 60000.0, p, rng()) is None
    # Never reached: no fill.
    assert evaluate_fill(bar(0, 60010, 60020, 60005, 60015), Side.LONG, 60000.0, p, rng()) is None


def test_gap_open_through_limit_fills_at_limit_not_better():
    p = MakerParams(fill_on="through")
    ev = evaluate_fill(bar(0, 59900, 59950, 59880, 59940), Side.LONG, 60000.0, p, rng())
    assert ev is not None
    assert ev.price == 60000.0  # a resting buy fills AT the limit, never better


def test_short_side_symmetry():
    p = MakerParams(fill_on="through", penetration_bps=1.0)
    ev = evaluate_fill(bar(0, 60000, 60010, 59995, 60005), Side.SHORT, 60000.0, p, rng())
    assert ev is not None and ev.swept          # high 60010 > 60006
    assert evaluate_fill(bar(0, 59990, 60000, 59980, 59995), Side.SHORT, 60000.0, p, rng()) is None


def test_touch_mode_is_the_optimistic_upper_bound():
    p = MakerParams(fill_on="touch")
    ev = evaluate_fill(bar(0, 60005, 60010, 60000, 60006), Side.LONG, 60000.0, p, rng())
    assert ev is not None and ev.fraction == 1.0


def test_prob_mode_probabilities_and_partials():
    always = MakerParams(fill_on="prob", touch_fill_prob=1.0, partial_fill_frac=0.5,
                         penetration_bps=100.0)  # pen $600 -> touch is never a sweep
    touched = bar(0, 60005, 60010, 60000, 60006)
    ev = evaluate_fill(touched, Side.LONG, 60000.0, always, rng())
    assert ev is not None and ev.fraction == 0.5 and not ev.swept
    never = MakerParams(fill_on="prob", touch_fill_prob=0.0, penetration_bps=100.0)
    assert evaluate_fill(touched, Side.LONG, 60000.0, never, rng()) is None
    # Swept fills fully regardless of probability:
    swept_bar = bar(0, 60000, 60010, 59000, 59500)
    ev = evaluate_fill(swept_bar, Side.LONG, 60000.0, never, rng())
    assert ev is not None and ev.fraction == 1.0


def test_dust_partials_ignored():
    p = MakerParams(fill_on="prob", touch_fill_prob=1.0, partial_fill_frac=0.05,
                    min_fill_frac=0.1, penetration_bps=100.0)
    assert evaluate_fill(bar(0, 60005, 60010, 60000, 60006), Side.LONG, 60000.0, p, rng()) is None


def test_params_validation():
    for bad in (
        dict(fill_on="psychic"), dict(limit_offset_bps=-1), dict(max_lifetime_bars=0),
        dict(touch_fill_prob=1.5), dict(partial_fill_frac=0.0), dict(min_fill_frac=2.0),
        dict(adverse_selection_bps=-0.1),
    ):
        with pytest.raises(ValueError):
            MakerParams(**bad).validate()
    for scenario in SCENARIOS.values():
        scenario.validate()  # shipped scenarios must be valid


# ---- engine integration ---------------------------------------------------------
def run_engine(bars, script, maker, limits=None, **cfg_over):
    cfg = BacktestConfig(initial_equity=100_000, fixed_stop_points=500.0,
                         stop_atr_mult=None, maker=maker, **cfg_over)
    engine = BacktestEngine(BTC, Scripted(script), limits or loose_limits(), cfg)
    return engine.run(bars), engine


def test_maker_fill_exact_arithmetic():
    maker = MakerParams(fill_on="through", penetration_bps=1.0,
                        max_lifetime_bars=3, adverse_selection_bps=0.0)
    bars = [
        bar(0, 60000, 60010, 59990, 60000),   # LONG signal at close
        bar(1, 60000, 60010, 59990, 60005),   # limit 60000; low 59990 sweeps -> fill
        bar(2, 60050, 60060, 60040, 60055),   # FLAT signal executes: taker exit at open
        bar(3, 60050, 60060, 60040, 60050),
    ]
    result, _ = run_engine(bars, {0: Side.LONG, 1: Side.FLAT}, maker)
    assert len(result.trades) == 1
    t = result.trades[0]
    assert t.entry_price == 60000.0                       # at the limit, no slippage
    assert t.size == pytest.approx(1.0)                   # $500 risk / $500 stop
    # maker entry fee + taker exit fee (exit at 60050 - 1bp -> 60044)
    assert t.exit_price == pytest.approx(60044.0)
    expected_fees = 0.00015 * 60000 * 1.0 + 0.00045 * 60044 * 1.0
    assert t.fees == pytest.approx(expected_fees)
    assert t.gross_pnl == pytest.approx(44.0)
    assert t.net_pnl == pytest.approx(44.0 - expected_fees)
    assert t.slippage_cost == pytest.approx(6.0)          # exit slippage only
    m = result.metrics["maker"]
    assert m["orders_placed"] == 1 and m["filled"] == 1 and m["fill_rate"] == 1.0
    assert result.metrics["execution_model"] == "maker_entry_taker_exit"


def test_missed_trade_stays_missed():
    maker = MakerParams(fill_on="through", max_lifetime_bars=3)
    # Price runs up and never comes back to the buy limit: the classic missed
    # winner. It must remain missed — no fill, no trade, ever.
    bars = [
        bar(0, 60000, 60010, 59995, 60005),   # LONG signal
        bar(1, 60010, 60050, 60005, 60040),   # limit 60010; never trades below
        bar(2, 60040, 60090, 60035, 60080),
        bar(3, 60080, 60150, 60070, 60140),
        bar(4, 60140, 60200, 60130, 60190),
    ]
    result, _ = run_engine(bars, {0: Side.LONG}, maker)
    assert result.trades == []
    m = result.metrics["maker"]
    assert m["orders_placed"] == 1
    assert m["filled"] == 0
    assert m["missed_expired"] == 1
    assert m["fill_rate"] == 0.0


def test_order_expires_after_lifetime_not_before():
    maker = MakerParams(fill_on="through", penetration_bps=1.0, max_lifetime_bars=2)
    bars = [
        bar(0, 60000, 60010, 59995, 60005),   # LONG signal
        bar(1, 60050, 60080, 60048, 60070),   # limit 60050; touched, never swept
        bar(2, 60060, 60090, 60046, 60080),   # still only touched -> still resting
        bar(3, 60070, 60100, 60000, 60090),   # WOULD sweep — but lifetime 2 expired
        bar(4, 60090, 60110, 60080, 60100),
    ]
    result, engine = run_engine(bars, {0: Side.LONG}, maker)
    # Lifetime 2 => evaluated on bars 1 and 2 only; the bar-3 sweep must not fill.
    assert result.trades == []
    assert result.metrics["maker"]["missed_expired"] == 1


def test_partial_fill_reduces_position_size():
    maker = MakerParams(fill_on="prob", touch_fill_prob=1.0, partial_fill_frac=0.5,
                        penetration_bps=100.0, max_lifetime_bars=3)
    bars = [
        bar(0, 60000, 60010, 59990, 60000),
        bar(1, 60005, 60010, 60000, 60006),   # touches limit 60000 exactly -> 50% fill
        bar(2, 60050, 60060, 60040, 60055),   # FLAT -> taker exit
        bar(3, 60050, 60060, 60040, 60050),
    ]
    result, _ = run_engine(bars, {0: Side.LONG, 1: Side.FLAT}, maker)
    assert len(result.trades) == 1
    assert result.trades[0].size == pytest.approx(0.5)    # planned 1.0, half filled
    assert result.metrics["maker"]["partial_fills"] == 1


def test_adverse_selection_charge_hits_net_pnl():
    base = MakerParams(fill_on="through", adverse_selection_bps=0.0)
    charged = MakerParams(fill_on="through", adverse_selection_bps=2.0)
    bars = [
        bar(0, 60000, 60010, 59990, 60000),
        bar(1, 60000, 60010, 59990, 60005),
        bar(2, 60050, 60060, 60040, 60055),
        bar(3, 60050, 60060, 60040, 60050),
    ]
    r0, _ = run_engine(bars, {0: Side.LONG, 1: Side.FLAT}, base)
    r2, _ = run_engine(bars, {0: Side.LONG, 1: Side.FLAT}, charged)
    expected_charge = 60000.0 * 1.0 * 2.0 / 10_000.0      # $12 on $60k notional
    assert r0.trades[0].net_pnl - r2.trades[0].net_pnl == pytest.approx(expected_charge)
    assert r2.trades[0].slippage_cost - r0.trades[0].slippage_cost == pytest.approx(expected_charge)


def test_same_bar_fill_then_stop_is_conservative():
    maker = MakerParams(fill_on="through")
    bars = [
        bar(0, 60000, 60010, 59990, 60000),
        bar(1, 60000, 60005, 59400, 59450),   # fills at 60000, then stop 59500 hits
        bar(2, 59450, 59500, 59400, 59480),
    ]
    result, _ = run_engine(bars, {0: Side.LONG}, maker)
    assert len(result.trades) == 1
    t = result.trades[0]
    assert t.exit_reason == "stop_loss"
    assert t.exit_ts == bars[1].ts                        # same bar as the fill
    assert t.exit_price == pytest.approx(59494.0)         # stop - 1bp slippage, tick-rounded


def test_new_opposite_signal_replaces_resting_order():
    maker = MakerParams(fill_on="through", max_lifetime_bars=5)
    bars = [
        bar(0, 60000, 60010, 59995, 60005),   # LONG signal -> buy limit rests
        bar(1, 60010, 60050, 60005, 60040),   # no fill; SHORT signal at close
        bar(2, 60040, 60090, 60041, 60080),   # buy limit canceled, sell limit placed & swept
        bar(3, 60080, 60100, 60070, 60090),
    ]
    result, _ = run_engine(bars, {0: Side.LONG, 1: Side.SHORT}, maker)
    m = result.metrics["maker"]
    assert m["replaced_by_signal"] == 1
    assert m["orders_placed"] == 2
    assert len(result.trades) == 1 and result.trades[0].direction is Side.SHORT


def test_kill_switch_prevents_resting_order_from_filling():
    maker = MakerParams(fill_on="through", max_lifetime_bars=10)
    ks = KillSwitch()
    cfg = BacktestConfig(initial_equity=100_000, fixed_stop_points=500.0,
                         stop_atr_mult=None, maker=maker)
    engine = BacktestEngine(BTC, Scripted({0: Side.LONG}), loose_limits(), cfg,
                            kill_switch=ks)
    engine.start()
    engine.step(bar(0, 60000, 60010, 59995, 60005))       # signal
    engine.step(bar(1, 60010, 60050, 60005, 60040))       # order rests, no fill
    ks.trip(KillSwitchReason.DATA_FEED_FAILURE, "external trip while order rests")
    engine.step(bar(2, 60005, 60010, 59500, 59600))       # would have swept the limit
    result = engine.finalize()
    assert result.trades == []                            # the fill was refused
    assert result.metrics["maker"]["canceled_by_risk"] >= 1


def test_daily_halt_blocks_new_maker_orders():
    limits = loose_limits(max_daily_loss=300.0)
    maker = MakerParams(fill_on="through")
    bars = [
        bar(0, 60000, 60010, 59990, 60000),   # LONG signal
        bar(1, 60000, 60005, 59400, 59450),   # fill + same-bar stop: big loss -> halt
        bar(2, 59450, 59500, 59400, 59480),   # LONG signal again (same day)
        bar(3, 59480, 59500, 59000, 59100),   # placement denied: no order, no fill
        bar(4, 59100, 59200, 59000, 59150),
    ]
    result, _ = run_engine(bars, {0: Side.LONG, 2: Side.LONG}, maker, limits=limits)
    assert len(result.trades) == 1
    assert result.metrics["maker"]["orders_placed"] == 1  # second order never placed


def test_deterministic_reproducibility_prob_mode():
    from trading_bot.data_pipeline.frames import frame_to_bars
    from trading_bot.research.experiments import generate_synthetic_bars

    synth = get_market("SYNTH")
    maker = MakerParams(fill_on="prob", touch_fill_prob=0.5, seed=11)
    from trading_bot.strategies.momentum import SimpleMomentum

    def run():
        cfg = BacktestConfig(initial_equity=50_000, stop_atr_mult=2.0, maker=maker)
        engine = BacktestEngine(synth, SimpleMomentum({"lookback": 5}),
                                loose_limits(), cfg)
        return engine.run(generate_synthetic_bars(n=400, seed=3, market_id="SYNTH"))

    a, b = run(), run()
    assert len(a.trades) == len(b.trades) > 0
    for ta, tb in zip(a.trades, b.trades):
        assert (ta.entry_ts, ta.exit_ts, ta.net_pnl) == (tb.entry_ts, tb.exit_ts, tb.net_pnl)
    assert a.metrics["maker"]["fill_rate"] == b.metrics["maker"]["fill_rate"]


def test_taker_path_unchanged_when_maker_is_none():
    # Backward compatibility: maker=None must produce the classic taker fills
    # (existing hand-computed suites also enforce this).
    bars = [
        bar(0, 60000, 60010, 59990, 60000),
        bar(1, 60000, 60010, 59990, 60005),
        bar(2, 60050, 60060, 60040, 60055),
        bar(3, 60050, 60060, 60040, 60050),
    ]
    result, _ = run_engine(bars, {0: Side.LONG, 1: Side.FLAT}, maker=None)
    t = result.trades[0]
    assert t.entry_price == pytest.approx(60006.0)        # taker: open + 1bp slippage
    assert "maker" not in result.metrics
    assert result.metrics["execution_model"] == "taker"


def test_maker_experiment_assumptions_are_logged_shape():
    maker = SCENARIOS["maker_baseline"]
    d = maker.describe()
    for key in ("execution", "fill_on", "limit_offset_bps", "max_lifetime_bars",
                "touch_fill_prob", "partial_fill_frac", "adverse_selection_bps", "seed"):
        assert key in d
