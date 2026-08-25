"""Trade-level ML datasets (Phase 11).

The ML question is "is this setup worth taking?" — so one row per TRADE of a
baseline strategy: the features known at the SIGNAL bar (the bar whose close
generated the signal), and the label from the trade's realized net P&L.

Leakage geometry, spelled out:
* A trade's ``entry_ts`` is the close time of the bar in which the fill
  happened (fills execute at that bar's open).
* The signal came from the PREVIOUS bar's close, so the feature row is the
  one at position ``index(entry_ts) - 1``.
* The feature matrix itself is leak-tested (tests/test_features.py), so a
  row at time t contains only information available at t.
Result: every feature in a row was known strictly before the entry fill.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from trading_bot.backtesting.engine import Trade


@dataclass
class TradeDataset:
    X: pd.DataFrame              # one row per trade, indexed by SIGNAL bar time
    y: pd.Series                 # True = trade was a net winner
    pnls: pd.Series              # realized net P&L per trade (economic evaluation)
    entry_ts: pd.DatetimeIndex   # entry bar close times (for time-ordered splits)
    n_skipped: int               # trades that could not be aligned to features

    def __len__(self) -> int:
        return len(self.X)


def build_trade_dataset(trades: list[Trade], features: pd.DataFrame) -> TradeDataset:
    """Align each trade with the feature row of its signal bar."""
    if not features.index.is_monotonic_increasing:
        raise ValueError("features index must be sorted in time")

    rows, wins, pnls, entries, signal_times = [], [], [], [], []
    skipped = 0
    locs = features.index.get_indexer(pd.DatetimeIndex([t.entry_ts for t in trades]))
    for trade, pos in zip(trades, locs):
        if pos <= 0:  # entry bar not in the matrix, or no prior bar to read
            skipped += 1
            continue
        row = features.iloc[pos - 1]
        if row.isna().all():
            skipped += 1
            continue
        rows.append(row.to_numpy(dtype=float))
        signal_times.append(features.index[pos - 1])
        wins.append(trade.net_pnl > 0)
        pnls.append(trade.net_pnl)
        entries.append(trade.entry_ts)

    if not rows:
        raise ValueError(
            "no trades could be aligned with the feature matrix — check that "
            "both were built from the same bar frame"
        )
    idx = pd.DatetimeIndex(signal_times, name="signal_ts")
    return TradeDataset(
        X=pd.DataFrame(np.vstack(rows), index=idx, columns=list(features.columns)),
        y=pd.Series(wins, index=idx, name="win"),
        pnls=pd.Series(pnls, index=idx, name="net_pnl"),
        entry_ts=pd.DatetimeIndex(entries, name="entry_ts"),
        n_skipped=skipped,
    )
