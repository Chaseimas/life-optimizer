"""Cross-market correlation of STRATEGY P&L streams (Phase 12).

What matters for diversification is not whether BTC and NQ prices correlate,
but whether the strategy's daily P&L streams across markets do. Both full-
sample and rolling correlations are reported, because crypto/equity
correlation regimes famously shift — one full-sample number can flatter a
portfolio that is correlated exactly when it hurts.
"""

from __future__ import annotations

import pandas as pd


def _align(daily_pnls: dict[str, pd.Series]) -> pd.DataFrame:
    """Outer-join daily P&L streams on date; a market with no trading that
    day contributed 0 P&L (not NaN — the strategy existed and did nothing)."""
    if len(daily_pnls) < 2:
        raise ValueError("need at least two markets to correlate")
    frame = pd.DataFrame(daily_pnls)
    return frame.fillna(0.0).sort_index()


def pnl_correlation_matrix(daily_pnls: dict[str, pd.Series]) -> pd.DataFrame:
    """Full-sample pairwise correlation of daily strategy P&L."""
    return _align(daily_pnls).corr()


def rolling_pnl_correlation(
    a: pd.Series, b: pd.Series, window_days: int = 30
) -> pd.Series:
    """Rolling correlation between two daily P&L streams."""
    frame = _align({"a": a, "b": b})
    return frame["a"].rolling(window_days, min_periods=window_days // 2).corr(frame["b"])


def correlation_summary(daily_pnls: dict[str, pd.Series], window_days: int = 30) -> dict:
    """Full-sample matrix plus, per pair, the worst (highest) rolling
    correlation — the number that actually bites in a drawdown."""
    matrix = pnl_correlation_matrix(daily_pnls)
    names = list(daily_pnls)
    pairs = {}
    for i, x in enumerate(names):
        for y in names[i + 1:]:
            roll = rolling_pnl_correlation(daily_pnls[x], daily_pnls[y], window_days)
            pairs[f"{x}|{y}"] = {
                "full_sample": float(matrix.loc[x, y]),
                "rolling_max": float(roll.max()) if roll.notna().any() else None,
                "rolling_min": float(roll.min()) if roll.notna().any() else None,
            }
    return {"matrix": matrix.to_dict(), "pairs": pairs, "window_days": window_days}
