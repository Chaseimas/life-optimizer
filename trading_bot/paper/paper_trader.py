"""Paper trader (Phase 13).

Drives the SAME ``BacktestEngine`` used for research — ``engine.step(bar)``
per completed bar from a feed — so signal logic, risk engine, position
sizing, stop logic and cost models are literally the same objects, not a
re-implementation. The only difference from a backtest is where the bars
come from.

Per session it writes, under one run directory:
* ``trades.jsonl``  — every closed trade: signal reason, entry (intended =
  bar open, actual = simulated fill), stop, target, size, exit, exit reason,
  fees, slippage, funding, net P&L.
* ``state.json``    — live engine snapshot after every bar (position, P&L
  vs limits, halts, kill-switch state) for the status dashboard.
* ``result.json``   — final metrics summary on shutdown.

Safety posture: there is NO order routing anywhere in this layer. A stale
feed trips the kill switch (data-feed failure = stop trading). The manual
sentinel file (``trading_bot/KILL_SWITCH``) halts a running session from
outside the process.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from trading_bot.backtesting.engine import BacktestConfig, BacktestEngine, BacktestResult, Trade
from trading_bot.core.config import RiskLimits
from trading_bot.core.market import MarketSpec
from trading_bot.monitoring.alerts import AlertManager
from trading_bot.monitoring.logging import get_logger
from trading_bot.paper.feeds import BarFeed, StaleFeedError
from trading_bot.risk.kill_switch import KillSwitch, KillSwitchReason
from trading_bot.strategies.base_strategy import BaseStrategy

log = get_logger("paper")


class PaperTrader:
    def __init__(
        self,
        spec: MarketSpec,
        strategy: BaseStrategy,
        limits: RiskLimits,
        config: BacktestConfig,
        feed: BarFeed,
        run_dir: str | Path,
        alerts: AlertManager | None = None,
        kill_switch: KillSwitch | None = None,
    ):
        self.spec = spec
        self.feed = feed
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.alerts = alerts or AlertManager()
        self.kill_switch = kill_switch or KillSwitch()
        self.engine = BacktestEngine(
            spec, strategy, limits, config, kill_switch=self.kill_switch
        )
        self._trades_path = self.run_dir / "trades.jsonl"
        self._state_path = self.run_dir / "state.json"
        self._result_path = self.run_dir / "result.json"

    # ---- persistence ---------------------------------------------------------
    def _write_trade(self, trade: Trade) -> None:
        record = asdict(trade)
        record["direction"] = trade.direction.name
        record["entry_ts"] = trade.entry_ts.isoformat()
        record["exit_ts"] = trade.exit_ts.isoformat()
        with open(self._trades_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

    def _write_state(self) -> None:
        state = self.engine.snapshot()
        state["written_at"] = datetime.now(timezone.utc).isoformat()
        state["market_id"] = self.spec.market_id
        state["mode"] = "PAPER"
        self._state_path.write_text(json.dumps(state, indent=2, default=str))

    # ---- run -----------------------------------------------------------------
    def run(self, max_bars: int | None = None,
            close_open_position_at_end: bool = True) -> BacktestResult:
        log.info(
            "PAPER session start: %s on %s -> %s (no orders are routed anywhere)",
            self.engine.strategy.name, self.spec.market_id, self.run_dir,
        )
        self.alerts.notify("info", "paper_session_start",
                           f"{self.engine.strategy.name} on {self.spec.market_id}")
        self.engine.start()
        n_halts_seen = 0
        kill_alerted = False
        n_bars = 0
        try:
            for bar in self.feed.stream():
                closed = self.engine.step(bar)
                for trade in closed:
                    self._write_trade(trade)
                    self.alerts.notify(
                        "info", "trade_closed",
                        f"{trade.direction.name} {trade.size} {trade.market_id} "
                        f"net {trade.net_pnl:+.2f} ({trade.exit_reason})",
                    )
                if len(self.engine.halts) > n_halts_seen:
                    for h in self.engine.halts[n_halts_seen:]:
                        self.alerts.notify("warning", "risk_halt", h)
                    n_halts_seen = len(self.engine.halts)
                if self.kill_switch.is_tripped and not kill_alerted:
                    self.alerts.notify("critical", "kill_switch",
                                       "kill switch engaged — trading halted")
                    kill_alerted = True
                self._write_state()
                n_bars += 1
                if max_bars is not None and n_bars >= max_bars:
                    log.info("max_bars=%d reached — ending paper session", max_bars)
                    break
        except StaleFeedError as e:
            self.kill_switch.trip(KillSwitchReason.DATA_FEED_FAILURE, str(e))
            self.alerts.notify("critical", "stale_feed", str(e))
        except KeyboardInterrupt:
            log.info("paper session interrupted by operator")
            self.alerts.notify("info", "paper_session_interrupted", "operator stop")

        result = self.engine.finalize(close_open_position=close_open_position_at_end)
        # Trades were written incrementally per bar; finalize() may have
        # force-closed one final position — write whatever is not on disk yet.
        written = self._count_written_trades()
        for trade in result.trades[written:]:
            self._write_trade(trade)
        self._write_state()
        summary = {
            "market_id": result.market_id,
            "strategy": result.strategy_name,
            "params": result.strategy_params,
            "n_bars": result.n_bars,
            "n_trades": len(result.trades),
            "metrics": {k: v for k, v in result.metrics.items()
                        if not isinstance(v, (list,))},
            "halts": result.halts,
            "mode": "PAPER",
        }
        self._result_path.write_text(json.dumps(summary, indent=2, default=str))
        self.alerts.notify(
            "info", "paper_session_end",
            f"{len(result.trades)} trades, net "
            f"{result.metrics['trade_net_profit']:+.2f} (simulated)",
        )
        return result

    def _count_written_trades(self) -> int:
        if not self._trades_path.exists():
            return 0
        with open(self._trades_path, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
