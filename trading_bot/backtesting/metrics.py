"""Performance metrics.

Pure functions over trade P&L sequences and daily P&L series. Implemented now
(Phase 1) because they are dependency-free math the whole system needs; the
full report generator (regime/time-of-day breakdowns etc.) arrives with the
backtester in Phases 5-8.

Conventions:
* Trade P&L values are NET (after fees/slippage/funding).
* ``periods_per_year`` defaults to 252 (futures trading days); use 365 for
  24/7 perps.
* Degenerate inputs return honest values: empty series -> zeros/None, zero
  volatility -> ratio of 0.0, profit factor with no losses -> None (not inf).
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
import pandas as pd

TRADING_DAYS_FUTURES = 252
TRADING_DAYS_CRYPTO = 365


# ---- trade-level ----------------------------------------------------------------
def trade_stats(pnls: Sequence[float]) -> dict:
    pnls = list(pnls)
    n = len(pnls)
    if n == 0:
        return {
            "n_trades": 0, "net_profit": 0.0, "gross_profit": 0.0, "gross_loss": 0.0,
            "profit_factor": None, "win_rate": None, "avg_win": None, "avg_loss": None,
            "expectancy": None, "max_consecutive_wins": 0, "max_consecutive_losses": 0,
        }
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = float(sum(wins))
    gross_loss = float(-sum(losses))  # positive number

    def _max_streak(predicate) -> int:
        best = cur = 0
        for p in pnls:
            cur = cur + 1 if predicate(p) else 0
            best = max(best, cur)
        return best

    return {
        "n_trades": n,
        "net_profit": float(sum(pnls)),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else None,
        "win_rate": len(wins) / n,
        "avg_win": (gross_profit / len(wins)) if wins else None,
        "avg_loss": (sum(losses) / len(losses)) if losses else None,
        "expectancy": float(sum(pnls)) / n,
        "max_consecutive_wins": _max_streak(lambda p: p > 0),
        "max_consecutive_losses": _max_streak(lambda p: p < 0),
    }


# ---- daily distribution ---------------------------------------------------------
def daily_stats(daily_pnl: pd.Series) -> dict:
    """Distribution of daily P&L — reported alongside the mean, never instead
    of it, so lumpy strategies can't hide behind an average."""
    s = daily_pnl.dropna()
    if len(s) == 0:
        return {
            "n_days": 0, "mean": None, "median": None, "std": None,
            "pct_profitable_days": None, "pct_losing_days": None,
            "best_day": None, "worst_day": None, "p5": None, "p95": None,
        }
    return {
        "n_days": int(len(s)),
        "mean": float(s.mean()),
        "median": float(s.median()),
        "std": float(s.std(ddof=1)) if len(s) > 1 else 0.0,
        "pct_profitable_days": float((s > 0).mean()),
        "pct_losing_days": float((s < 0).mean()),
        "best_day": float(s.max()),
        "worst_day": float(s.min()),
        "p5": float(s.quantile(0.05)),
        "p95": float(s.quantile(0.95)),
    }


# ---- risk-adjusted ratios -------------------------------------------------------
def sharpe_ratio(returns: pd.Series, periods_per_year: int = TRADING_DAYS_FUTURES) -> float:
    r = returns.dropna()
    if len(r) < 2:
        return 0.0
    sd = r.std(ddof=1)
    # Treat numerically-zero volatility as zero (constant series produce
    # ~1e-18 std from float error, which would explode the ratio).
    if math.isnan(sd) or sd < 1e-15:
        return 0.0
    return float(r.mean() / sd * np.sqrt(periods_per_year))


def sortino_ratio(returns: pd.Series, periods_per_year: int = TRADING_DAYS_FUTURES) -> float:
    r = returns.dropna()
    if len(r) < 2:
        return 0.0
    downside = r[r < 0]
    if len(downside) == 0:
        return 0.0  # undefined without losses; report 0 rather than infinity
    dd = np.sqrt((downside**2).mean())
    if math.isnan(dd) or dd < 1e-15:
        return 0.0
    return float(r.mean() / dd * np.sqrt(periods_per_year))


def equity_curve(daily_pnl: pd.Series, starting_equity: float) -> pd.Series:
    return starting_equity + daily_pnl.fillna(0.0).cumsum()


def max_drawdown(equity: pd.Series) -> dict:
    """Max peak-to-trough drawdown, absolute and as a fraction of the peak."""
    e = equity.dropna()
    if len(e) == 0:
        return {"max_drawdown_abs": 0.0, "max_drawdown_pct": 0.0}
    peak = e.cummax()
    dd_abs = peak - e
    with np.errstate(divide="ignore", invalid="ignore"):
        dd_pct = dd_abs / peak.replace(0, np.nan)
    return {
        "max_drawdown_abs": float(dd_abs.max()),
        "max_drawdown_pct": float(dd_pct.max()) if dd_pct.notna().any() else 0.0,
    }


def calmar_ratio(annual_return_pct: float, max_dd_pct: float) -> float:
    if max_dd_pct <= 0:
        return 0.0
    return float(annual_return_pct / max_dd_pct)


# ---- combined summary -----------------------------------------------------------
def summarize(
    trade_pnls: Sequence[float],
    daily_pnl: pd.Series,
    starting_equity: float,
    periods_per_year: int = TRADING_DAYS_FUTURES,
) -> dict:
    """Core summary. The full report (monthly/yearly tables, long-vs-short,
    time-of-day, regime attribution, walk-forward and Monte Carlo sections)
    arrives with Phases 5-10 and will extend this dict."""
    tstats = trade_stats(trade_pnls)
    dstats = daily_stats(daily_pnl)
    eq = equity_curve(daily_pnl, starting_equity)
    dd = max_drawdown(eq)
    daily_ret = daily_pnl / eq.shift(1).fillna(starting_equity)
    n_days = max(len(daily_pnl.dropna()), 1)
    total_return = (eq.iloc[-1] / starting_equity - 1.0) if len(eq) else 0.0
    annualized = (1.0 + total_return) ** (periods_per_year / n_days) - 1.0 if n_days else 0.0
    return {
        **{f"trade_{k}": v for k, v in tstats.items()},
        **{f"daily_{k}": v for k, v in dstats.items()},
        "sharpe": sharpe_ratio(daily_ret, periods_per_year),
        "sortino": sortino_ratio(daily_ret, periods_per_year),
        "calmar": calmar_ratio(annualized, dd["max_drawdown_pct"]),
        "annualized_return_pct": float(annualized),
        **dd,
        "final_equity": float(eq.iloc[-1]) if len(eq) else starting_equity,
    }
