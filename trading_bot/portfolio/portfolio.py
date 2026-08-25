"""Portfolio engine (Phase 12): does diversification actually EARN its place?

Takes per-market backtest results of the same (or different) strategies and
answers, with numbers: is the weighted combination better than the best
single market on Sharpe, Sortino, drawdown and return stability — or is it
just more trades? Markets are never added for activity's sake; the verdict
says explicitly whether the combination is justified.

Assumption (stated): per-market daily P&L streams scale linearly with their
weight (valid when weights scale the per-market risk fraction and each
market's sizing is independent, as in this system). The combined stream is
the weighted sum on aligned dates.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from trading_bot.backtesting.metrics import max_drawdown, sharpe_ratio, sortino_ratio, summarize
from trading_bot.portfolio.correlation import _align, pnl_correlation_matrix


@dataclass
class PortfolioComparison:
    weights: dict                 # market -> weight (sum 1.0)
    per_market: dict              # market -> metrics dict
    combined: dict                # metrics of the weighted portfolio
    best_single: str              # market with the best single Sharpe
    correlation: dict             # full-sample correlation matrix (as dict)
    verdict: str

    @property
    def diversification_helps(self) -> bool:
        return self.verdict.startswith("DIVERSIFY")


def compare_portfolio(
    daily_pnls: dict[str, pd.Series],
    *,
    initial_equity: float,
    weights: dict[str, float] | None = None,
    periods_per_year: int = 365,
    min_sharpe_improvement: float = 0.1,
) -> PortfolioComparison:
    """Compare each market alone vs the weighted combination.

    ``daily_pnls``: market -> daily P&L series from backtests run with the
    SAME initial equity and cost assumptions (compare like with like).
    """
    names = list(daily_pnls)
    if len(names) < 2:
        raise ValueError("portfolio comparison needs at least two markets")
    if weights is None:
        weights = {m: 1.0 / len(names) for m in names}
    if set(weights) != set(names):
        raise ValueError("weights must cover exactly the given markets")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("weights must sum to a positive value")
    weights = {m: w / total for m, w in weights.items()}

    aligned = _align(daily_pnls)

    def metrics_of(daily: pd.Series) -> dict:
        return summarize([], daily, initial_equity, periods_per_year=periods_per_year)

    per_market = {m: metrics_of(aligned[m]) for m in names}
    combined_daily = sum(aligned[m] * weights[m] for m in names)
    combined = metrics_of(combined_daily)

    best_single = max(names, key=lambda m: per_market[m]["sharpe"])
    best = per_market[best_single]

    sharpe_gain = combined["sharpe"] - best["sharpe"]
    dd_change = combined["max_drawdown_pct"] - best["max_drawdown_pct"]

    if combined["sharpe"] <= 0:
        verdict = (
            f"NO BASIS: the combined portfolio has non-positive Sharpe "
            f"({combined['sharpe']:.2f}) — diversifying strategies without an "
            "edge just diversifies the losses."
        )
    elif sharpe_gain >= min_sharpe_improvement and dd_change <= 0.0:
        verdict = (
            f"DIVERSIFY: combined Sharpe {combined['sharpe']:.2f} vs best single "
            f"({best_single}) {best['sharpe']:.2f} (+{sharpe_gain:.2f}), max "
            f"drawdown {combined['max_drawdown_pct']:.1%} vs {best['max_drawdown_pct']:.1%}."
        )
    else:
        verdict = (
            f"CONCENTRATE: best single market ({best_single}, Sharpe "
            f"{best['sharpe']:.2f}) is not beaten by the combination "
            f"(Sharpe {combined['sharpe']:.2f}, drawdown change {dd_change:+.1%}) "
            "— adding markets here only adds trades, not quality."
        )

    return PortfolioComparison(
        weights=weights,
        per_market=per_market,
        combined=combined,
        best_single=best_single,
        correlation=pnl_correlation_matrix(daily_pnls).to_dict(),
        verdict=verdict,
    )
