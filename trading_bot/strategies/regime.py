"""Market regime classification (trend / mean-reversion / volatility state).

STATUS: not implemented — Phase 7 (used as a filter for the other baselines).

Planned design:
* Simple, transparent regime measures first: rolling trend strength (e.g.
  efficiency ratio), realized-volatility percentile, volatility
  expansion/contraction flags.
* Regime labels must be computable strictly from past data at every bar
  (verified by the look-ahead tests) — regime classifiers are a classic
  source of subtle leakage.
* Output feeds other strategies as a filter and feeds performance
  attribution ("performance by market regime" in reports).
"""

from __future__ import annotations

from trading_bot.strategies.base_strategy import BaseStrategy


class RegimeClassifier(BaseStrategy):
    name = "regime"

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "RegimeClassifier is scheduled for Phase 7. "
            "It has not been implemented or tested; no results exist."
        )

    @property
    def warmup_bars(self) -> int:  # pragma: no cover
        raise NotImplementedError

    def on_bar(self, bar):  # pragma: no cover
        raise NotImplementedError
