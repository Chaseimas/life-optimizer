"""Beta / random-entry controls (repo-grade version of the Pass-1/2 scratch
implementations).

The control question: does the strategy's ENTRY TIMING add anything beyond
holding this market with this sizing, these costs, and these mechanics? For
each actual trade we schedule a random entry with the same direction and
holding time, run it through the SAME engine (same execution model, stops,
sizing, risk limits, funding), and compare the actual result against the
distribution over many replicates.

Interpretation bar (pre-registered): a candidate must reach at least the
95th percentile of the null distribution. 50th–90th is what market drift
looks like.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from trading_bot.backtesting.engine import BacktestConfig, BacktestEngine, Trade
from trading_bot.core.config import RiskLimits
from trading_bot.core.events import Bar, Signal
from trading_bot.core.market import MarketSpec
from trading_bot.core.types import Side
from trading_bot.strategies.base_strategy import BaseStrategy


class RandomTimedEntries(BaseStrategy):
    """Signals at pre-drawn bar indexes with pre-drawn directions and timed
    flat exits. Everything else (fills, stops, sizing, costs) is supplied by
    the engine, identically to the strategy under test."""

    name = "random_control"

    def __init__(self, schedule: dict[int, tuple[Side, int]]):
        self.params = {}
        self.schedule = schedule
        self.i = -1
        self.flat_at: int | None = None

    @property
    def warmup_bars(self) -> int:
        return 0

    def on_bar(self, bar: Bar) -> Signal | None:
        self.i += 1
        if self.flat_at is not None and self.i >= self.flat_at:
            self.flat_at = None
            return Signal(ts=bar.ts, market_id=bar.market_id, direction=Side.FLAT,
                          reason="control timed exit")
        if self.i in self.schedule and self.flat_at is None:
            direction, hold = self.schedule[self.i]
            self.flat_at = self.i + hold
            return Signal(ts=bar.ts, market_id=bar.market_id, direction=direction,
                          reason="control random entry")
        return None

    def reset(self) -> None:
        self.i = -1
        self.flat_at = None


@dataclass(frozen=True)
class ControlResult:
    actual_net: float
    n_profile_trades: int
    n_replicates: int
    null_mean: float
    null_p5: float
    null_p50: float
    null_p95: float
    actual_percentile: float

    @property
    def separates(self) -> bool:
        return self.actual_percentile >= 0.95

    def describe(self) -> dict:
        return {
            "actual_net": round(self.actual_net, 2),
            "n_profile_trades": self.n_profile_trades,
            "n_replicates": self.n_replicates,
            "null_mean": round(self.null_mean, 2),
            "null_p5": round(self.null_p5, 2),
            "null_p50": round(self.null_p50, 2),
            "null_p95": round(self.null_p95, 2),
            "actual_percentile": round(self.actual_percentile, 3),
            "separates_at_95": self.separates,
        }


def run_random_entry_control(
    *,
    spec: MarketSpec,
    bars: list[Bar],
    trades: list[Trade],
    bt_config: BacktestConfig,
    limits: RiskLimits,
    funding: pd.Series | None = None,
    directions: tuple[Side, ...] = (Side.LONG, Side.SHORT),
    n_replicates: int = 200,
    seed: int = 2026,
    warmup_bars: int = 20,
) -> ControlResult:
    """Random-entry null distribution matched to the given trades' directions
    and holding times, with identical engine mechanics."""
    profile = [(t.direction, max(t.bars_held, 1)) for t in trades
               if t.direction in directions]
    if not profile:
        raise ValueError("no trades match the requested directions")
    actual_net = float(sum(t.net_pnl for t in trades if t.direction in directions))

    rng = np.random.default_rng(seed)
    n = len(bars)
    nets = np.empty(n_replicates)
    for rep in range(n_replicates):
        order = rng.permutation(len(profile))
        schedule: dict[int, tuple[Side, int]] = {}
        blocked: set[int] = set()
        for k in order:
            direction, hold = profile[k]
            for _attempt in range(80):
                idx = int(rng.integers(warmup_bars, max(warmup_bars + 1, n - hold - 2)))
                span = range(idx, idx + hold + 2)
                if not any(s in blocked for s in span):
                    schedule[idx] = (direction, hold)
                    blocked.update(span)
                    break
        engine = BacktestEngine(spec, RandomTimedEntries(schedule), limits,
                                bt_config, funding=funding)
        nets[rep] = engine.run(bars).metrics["trade_net_profit"]

    return ControlResult(
        actual_net=actual_net,
        n_profile_trades=len(profile),
        n_replicates=n_replicates,
        null_mean=float(nets.mean()),
        null_p5=float(np.percentile(nets, 5)),
        null_p50=float(np.percentile(nets, 50)),
        null_p95=float(np.percentile(nets, 95)),
        actual_percentile=float((nets < actual_net).mean()),
    )
