"""Baseline reference for ML comparisons (Phase 11).

The baseline against which every ML setup filter is judged is deliberately
trivial: TAKE EVERY SETUP the underlying strategy generates. If a filter
cannot beat "just take them all" on held-out trades, it is rejected —
regardless of how sophisticated it is. The comparison protocol lives in
``research/ml_experiment.py``; this module holds the baseline itself so the
concept has one named home.
"""

from __future__ import annotations

from typing import Sequence

from trading_bot.backtesting.metrics import trade_stats


def always_take_baseline(trade_pnls: Sequence[float]) -> dict:
    """Statistics of taking every setup — the bar any ML filter must clear
    out-of-sample."""
    return trade_stats(list(trade_pnls))
