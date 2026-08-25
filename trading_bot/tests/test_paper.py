"""Phase 13/14: the paper trader must be the SAME machine as the backtester
(equivalence proven, not promised), feeds must never emit forming bars, and
failures must trip the kill switch — plus session artifacts and alerts."""

from __future__ import annotations

import json
from datetime import timedelta

import pandas as pd
import pytest

from trading_bot.backtesting.engine import BacktestConfig, BacktestEngine
from trading_bot.core.config import RiskLimits
from trading_bot.core.market import get_market
from trading_bot.data_pipeline.frames import bars_to_frame
from trading_bot.monitoring.alerts import AlertManager, CollectingSink
from trading_bot.monitoring.dashboard import format_status
from trading_bot.paper.feeds import HyperliquidPollingFeed, ReplayFeed, StaleFeedError
from trading_bot.paper.paper_trader import PaperTrader
from trading_bot.research.experiments import generate_synthetic_bars
from trading_bot.risk.kill_switch import KillSwitch, KillSwitchReason
from trading_bot.strategies.momentum import SimpleMomentum

SYNTH = get_market("SYNTH")

LIMITS = RiskLimits(
    max_daily_loss=1e9, max_risk_per_trade=0.005, max_position_size=1e6,
    max_trades_per_day=10_000, max_drawdown=0.99, max_open_exposure=1e12,
    max_consecutive_losses=10_000,
)
CFG = BacktestConfig(initial_equity=50_000, stop_atr_mult=2.0, atr_period=14)


@pytest.fixture(scope="module")
def bars():
    return generate_synthetic_bars(n=800, seed=17, market_id="SYNTH")


# ---- the equivalence guarantee --------------------------------------------------
def test_paper_equals_backtest_on_identical_bars(bars, tmp_path):
    """Same bars in, same trades out — paper and backtest share one engine."""
    backtest = BacktestEngine(SYNTH, SimpleMomentum({"lookback": 5}), LIMITS, CFG).run(bars)

    trader = PaperTrader(
        spec=SYNTH, strategy=SimpleMomentum({"lookback": 5}), limits=LIMITS,
        config=CFG, feed=ReplayFeed(bars_to_frame(bars), "SYNTH"),
        run_dir=tmp_path / "run",
    )
    paper = trader.run()

    assert len(paper.trades) == len(backtest.trades) > 0
    for a, b in zip(paper.trades, backtest.trades):
        assert (a.entry_ts, a.exit_ts, a.direction, a.size) == \
               (b.entry_ts, b.exit_ts, b.direction, b.size)
        assert a.net_pnl == pytest.approx(b.net_pnl)
    assert paper.metrics["final_equity"] == pytest.approx(backtest.metrics["final_equity"])


# ---- session artifacts ----------------------------------------------------------
def test_session_artifacts_written(bars, tmp_path):
    run_dir = tmp_path / "run"
    sink = CollectingSink()
    trader = PaperTrader(
        spec=SYNTH, strategy=SimpleMomentum({"lookback": 5}), limits=LIMITS,
        config=CFG, feed=ReplayFeed(bars_to_frame(bars), "SYNTH"),
        run_dir=run_dir, alerts=AlertManager([sink]),
    )
    result = trader.run()

    lines = [json.loads(l) for l in (run_dir / "trades.jsonl").read_text().splitlines() if l]
    assert len(lines) == len(result.trades)
    required = {"entry_ts", "exit_ts", "entry_price", "exit_price", "size", "direction",
                "stop_price", "tp_price", "entry_reason", "exit_reason", "fees",
                "slippage_cost", "funding", "net_pnl"}
    assert required <= set(lines[0])

    state = json.loads((run_dir / "state.json").read_text())
    assert state["mode"] == "PAPER"
    assert state["n_trades"] == len(result.trades)
    assert state["kill_switch_tripped"] is False

    summary = json.loads((run_dir / "result.json").read_text())
    assert summary["mode"] == "PAPER"
    assert summary["n_trades"] == len(result.trades)

    events = [a.event for a in sink.alerts]
    assert "paper_session_start" in events
    assert "paper_session_end" in events
    # One alert per trade closed during the loop; a finalize() force-close
    # (exit_reason end_of_data) happens after the loop and is not alerted.
    n_loop_trades = sum(1 for t in result.trades if t.exit_reason != "end_of_data")
    assert events.count("trade_closed") == n_loop_trades > 0


def test_max_bars_stops_the_session(bars, tmp_path):
    trader = PaperTrader(
        spec=SYNTH, strategy=SimpleMomentum({"lookback": 5}), limits=LIMITS,
        config=CFG, feed=ReplayFeed(bars_to_frame(bars), "SYNTH"),
        run_dir=tmp_path / "run",
    )
    result = trader.run(max_bars=100)
    assert result.n_bars == 100


# ---- kill switch paths ----------------------------------------------------------
def test_manual_sentinel_halts_paper_session(bars, tmp_path):
    sentinel = tmp_path / "KILL_SWITCH"
    sentinel.touch()  # engaged before the session even starts
    sink = CollectingSink()
    trader = PaperTrader(
        spec=SYNTH, strategy=SimpleMomentum({"lookback": 5}), limits=LIMITS,
        config=CFG, feed=ReplayFeed(bars_to_frame(bars[:100]), "SYNTH"),
        run_dir=tmp_path / "run", alerts=AlertManager([sink]),
        kill_switch=KillSwitch(manual_file=sentinel),
    )
    result = trader.run()
    assert len(result.trades) == 0                       # no entries while tripped
    state = json.loads((tmp_path / "run" / "state.json").read_text())
    assert state["kill_switch_tripped"] is True
    assert "kill_switch" in [a.event for a in sink.alerts]


class _DyingFeed(ReplayFeed):
    def __init__(self, df, market_id, die_after: int):
        super().__init__(df, market_id)
        self.die_after = die_after

    def stream(self):
        for i, bar in enumerate(super().stream()):
            if i >= self.die_after:
                raise StaleFeedError("simulated feed death")
            yield bar


def test_stale_feed_trips_kill_switch(bars, tmp_path):
    ks = KillSwitch()
    sink = CollectingSink()
    trader = PaperTrader(
        spec=SYNTH, strategy=SimpleMomentum({"lookback": 5}), limits=LIMITS,
        config=CFG, feed=_DyingFeed(bars_to_frame(bars), "SYNTH", die_after=50),
        run_dir=tmp_path / "run", alerts=AlertManager([sink]), kill_switch=ks,
    )
    result = trader.run()
    assert ks.is_tripped
    assert ks.history[-1].reason is KillSwitchReason.DATA_FEED_FAILURE
    assert result.n_bars == 50
    assert "stale_feed" in [a.event for a in sink.alerts]


# ---- polling feed: completed bars only, staleness detection ---------------------
def test_polling_feed_never_emits_forming_bars():
    H = pd.Timedelta(hours=1)
    t0 = pd.Timestamp("2026-01-05 00:00", tz="UTC")

    def mk_frame(n_completed, forming: bool):
        n = n_completed + (1 if forming else 0)
        idx = pd.DatetimeIndex([t0 + H * (i + 1) for i in range(n)], tz="UTC", name="ts")
        return pd.DataFrame(
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 10.0},
            index=idx,
        )

    polls = {"n": 0}
    now_seq = [t0 + H * 12 + pd.Timedelta(minutes=30),   # 12 bars closed, 13th forming
               t0 + H * 13 + pd.Timedelta(minutes=30),   # 13th closed, 14th forming
               t0 + H * 18]                              # nothing new -> stale

    def now_fn():
        return now_seq[min(polls["n"], len(now_seq) - 1)]

    def fetch_fn(coin, interval, start, end):
        frames = [mk_frame(12, forming=True), mk_frame(13, forming=True),
                  mk_frame(14, forming=False)]
        f = frames[min(polls["n"], 2)]
        polls["n"] += 1
        return f

    feed = HyperliquidPollingFeed(
        "BTC", "1h", "HL:BTC", warmup_bars=20, max_polls=3,
        fetch_fn=fetch_fn, now_fn=now_fn, sleep_fn=lambda s: None,
    )
    got = []
    with pytest.raises(StaleFeedError):
        for bar in feed.stream():
            got.append(bar)

    # Poll 1: 12 completed. Poll 2: exactly 1 new. Poll 3: 1 more, then stale.
    assert len(got) == 14
    ts_list = [b.ts for b in got]
    assert ts_list == sorted(ts_list)
    assert len(set(ts_list)) == 14                        # no duplicates
    # The forming candle (close time in the future at poll time) never appeared:
    assert max(ts_list) == (t0 + H * 14).to_pydatetime()


# ---- dashboard ------------------------------------------------------------------
def test_dashboard_renders(bars, tmp_path):
    run_dir = tmp_path / "run"
    trader = PaperTrader(
        spec=SYNTH, strategy=SimpleMomentum({"lookback": 5}), limits=LIMITS,
        config=CFG, feed=ReplayFeed(bars_to_frame(bars[:200]), "SYNTH"),
        run_dir=run_dir,
    )
    trader.run()
    state = json.loads((run_dir / "state.json").read_text())
    trades = [json.loads(l) for l in (run_dir / "trades.jsonl").read_text().splitlines() if l]
    text = format_status(state, trades)
    assert "PAPER SESSION STATUS" in text
    assert "kill switch" in text
