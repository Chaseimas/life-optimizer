"""Experiment runners.

Phase 1 contains exactly one runner: a PIPELINE SMOKE TEST that pushes
synthetic random-walk bars through a strategy, aligns each signal with the
NEXT bar's return (no peeking), and logs the outcome to the experiment log.

What this is:   proof that data -> strategy -> evaluation -> experiment-log
                plumbing works end-to-end with no look-ahead.
What this is NOT: a backtest. There are no fees, no slippage, no position
                sizing and no real data here. On synthetic random walks any
                measured "edge" is noise — and the runner says so in its own
                results. Real backtests arrive with Phases 2-7.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from trading_bot.core.events import Bar
from trading_bot.core.types import Side
from trading_bot.research.experiment_log import ExperimentLog
from trading_bot.strategies.base_strategy import BaseStrategy


def generate_synthetic_bars(
    n: int = 2000,
    seed: int = 42,
    market_id: str = "SYNTH",
    start: datetime | None = None,
    freq_minutes: int = 5,
    s0: float = 10_000.0,
    vol_per_bar: float = 0.001,
) -> list[Bar]:
    """Seeded geometric random-walk OHLCV bars (a market with NO edge by
    construction — the correct null instrument for pipeline tests)."""
    rng = np.random.default_rng(seed)
    start = start or datetime(2024, 1, 1, tzinfo=timezone.utc)
    rets = rng.normal(0.0, vol_per_bar, size=n)
    closes = s0 * np.exp(np.cumsum(rets))
    bars: list[Bar] = []
    prev_close = s0
    for i in range(n):
        c = float(closes[i])
        o = prev_close
        hi = max(o, c) * float(1 + abs(rng.normal(0, vol_per_bar / 2)))
        lo = min(o, c) * float(1 - abs(rng.normal(0, vol_per_bar / 2)))
        bars.append(
            Bar(
                ts=start + timedelta(minutes=freq_minutes * (i + 1)),
                market_id=market_id,
                open=o, high=hi, low=lo, close=c,
                volume=float(rng.integers(100, 10_000)),
            )
        )
        prev_close = c
    return bars


def run_signal_smoke_experiment(
    strategy: BaseStrategy,
    bars: list[Bar],
    experiment_log: ExperimentLog,
    dataset: str,
    notes: str = "",
) -> dict:
    """Feed bars chronologically, collect signals, evaluate each against the
    NEXT bar's close-to-close return (gross, return-space, cost-free)."""
    strategy.reset()
    signals: list[tuple[int, Side]] = []
    for i, bar in enumerate(bars):
        sig = strategy.on_bar(bar)
        if sig is not None and sig.direction is not Side.FLAT:
            if sig.ts != bar.ts:
                raise AssertionError(
                    "look-ahead guard: signal timestamp must equal the bar close time"
                )
            signals.append((i, sig.direction))

    aligned_returns = []
    hits = 0
    for i, direction in signals:
        if i + 1 >= len(bars):
            continue  # last bar has no future — that signal is unevaluated, not peeked
        next_ret = bars[i + 1].close / bars[i].close - 1.0
        directional = next_ret * int(direction)
        aligned_returns.append(directional)
        if directional > 0:
            hits += 1

    n_eval = len(aligned_returns)
    results = {
        "n_bars": len(bars),
        "n_signals": len(signals),
        "n_evaluated": n_eval,
        "hit_rate": (hits / n_eval) if n_eval else None,
        "mean_next_bar_return": (float(np.mean(aligned_returns)) if n_eval else None),
        "evaluation": (
            "PLUMBING CHECK ONLY: gross next-bar returns in return space; no "
            "fees, slippage, sizing or risk. Not a backtest, not evidence of "
            "an edge."
        ),
    }

    record = experiment_log.log(
        strategy=strategy.name,
        market=bars[0].market_id if bars else "unknown",
        params=strategy.params,
        dataset=dataset,
        results=results,
        notes=notes,
    )
    results["experiment_id"] = record.experiment_id
    return results
