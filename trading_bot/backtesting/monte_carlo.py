"""Monte Carlo analysis of a backtest's trade sequence (Phase 10).

One historical equity curve is a sample of size one. Resampling the realized
trades answers: how bad could the SAME trades have been in a different order
(shuffle), and how bad could a strategy with this trade distribution get
(bootstrap)?

* method="shuffle": permutes trade order. Total P&L is preserved; drawdowns
  and losing streaks vary. Isolates sequencing risk.
* method="bootstrap": resamples trades with replacement. Total P&L varies
  too — a rough distribution over alternate histories, under the (strong,
  stated) assumption that trades are i.i.d. draws from the realized set.

Nothing here improves a strategy — it only widens honest error bars around
what a backtest showed. A strategy is judged on out-of-sample results first;
Monte Carlo then estimates the pain of holding it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

PERCENTILES = (50, 90, 95, 99)


@dataclass(frozen=True)
class MonteCarloReport:
    method: str
    n_sims: int
    n_trades: int
    initial_equity: float
    # Max drawdown across each simulated path (absolute currency):
    drawdown_percentiles: dict          # {50: ..., 90: ..., 95: ..., 99: ..., "worst": ...}
    # Final P&L across paths:
    final_pnl_percentiles: dict         # {5: ..., 50: ..., 95: ...}
    prob_final_negative: float
    # Longest losing streak across paths:
    losing_streak_percentiles: dict     # {50: ..., 95: ..., "worst": ...}
    # Probability the path ever lost `ruin_drawdown` of initial equity:
    ruin_drawdown: float
    prob_ruin: float
    assumptions: str = (
        "Trades treated as exchangeable (shuffle) / i.i.d. (bootstrap); real "
        "markets have regime dependence these resamples cannot capture. "
        "Estimates are error bars, not guarantees."
    )


def _longest_negative_runs(pnl_matrix: np.ndarray) -> np.ndarray:
    """Longest run of losing trades per row, vectorized across rows."""
    neg = pnl_matrix < 0
    best = np.zeros(neg.shape[0], dtype=np.int64)
    run = np.zeros(neg.shape[0], dtype=np.int64)
    for j in range(neg.shape[1]):
        run = np.where(neg[:, j], run + 1, 0)
        best = np.maximum(best, run)
    return best


def monte_carlo_trades(
    trade_pnls: Sequence[float],
    *,
    initial_equity: float,
    n_sims: int = 10_000,
    method: str = "shuffle",
    ruin_drawdown: float = 0.5,
    seed: int = 42,
) -> MonteCarloReport:
    pnls = np.asarray(list(trade_pnls), dtype=np.float64)
    if len(pnls) < 5:
        raise ValueError(
            f"Monte Carlo needs a meaningful trade sample (got {len(pnls)}); "
            "run it on strategies that actually traded."
        )
    if method not in ("shuffle", "bootstrap"):
        raise ValueError("method must be 'shuffle' or 'bootstrap'")
    if not (0 < ruin_drawdown < 1):
        raise ValueError("ruin_drawdown must be a fraction in (0, 1)")

    rng = np.random.default_rng(seed)
    n = len(pnls)
    if method == "shuffle":
        sims = np.tile(pnls, (n_sims, 1))
        sims = rng.permuted(sims, axis=1)
    else:
        sims = rng.choice(pnls, size=(n_sims, n), replace=True)

    cum = np.cumsum(sims, axis=1)
    running_peak = np.maximum.accumulate(np.maximum(cum, 0.0), axis=1)
    drawdowns = running_peak - cum                       # absolute, per step
    max_dd = drawdowns.max(axis=1)
    final = cum[:, -1]
    streaks = _longest_negative_runs(sims)

    # Ruin: equity path (from initial) ever down `ruin_drawdown` from initial.
    path_min = initial_equity + cum.min(axis=1, initial=0.0)
    ruined = path_min <= initial_equity * (1.0 - ruin_drawdown)

    return MonteCarloReport(
        method=method,
        n_sims=n_sims,
        n_trades=n,
        initial_equity=initial_equity,
        drawdown_percentiles={
            **{f"p{p}": float(np.percentile(max_dd, p)) for p in PERCENTILES},
            "worst": float(max_dd.max()),
        },
        final_pnl_percentiles={
            "p5": float(np.percentile(final, 5)),
            "p50": float(np.percentile(final, 50)),
            "p95": float(np.percentile(final, 95)),
        },
        prob_final_negative=float((final < 0).mean()),
        losing_streak_percentiles={
            "p50": float(np.percentile(streaks, 50)),
            "p95": float(np.percentile(streaks, 95)),
            "worst": int(streaks.max()),
        },
        ruin_drawdown=ruin_drawdown,
        prob_ruin=float(ruined.mean()),
    )


def format_monte_carlo(report: MonteCarloReport) -> str:
    dd = report.drawdown_percentiles
    fp = report.final_pnl_percentiles
    ls = report.losing_streak_percentiles
    return "\n".join(
        [
            "-" * 72,
            f"MONTE CARLO ({report.method}, {report.n_sims} sims over "
            f"{report.n_trades} trades)",
            f"  max drawdown:   p50 {dd['p50']:,.0f}   p90 {dd['p90']:,.0f}   "
            f"p95 {dd['p95']:,.0f}   p99 {dd['p99']:,.0f}   worst {dd['worst']:,.0f}",
            f"  final P&L:      p5 {fp['p5']:,.0f}   p50 {fp['p50']:,.0f}   p95 {fp['p95']:,.0f}   "
            f"P(final<0) = {report.prob_final_negative:.1%}",
            f"  losing streak:  p50 {ls['p50']:.0f}   p95 {ls['p95']:.0f}   worst {ls['worst']}",
            f"  P(drawdown >= {report.ruin_drawdown:.0%} of equity) = {report.prob_ruin:.2%}",
            f"  NOTE: {report.assumptions}",
            "-" * 72,
        ]
    )
