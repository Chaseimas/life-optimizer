"""Mean reversion strategy.

STATUS: not implemented — Phase 7 (baseline strategies), tested against data
from Phases 2-4 first.

Planned design:
* Fade extensions from a rolling mean, normalized by realized volatility
  (z-score of price vs. rolling mean / rolling std).
* Entry only in mean-reverting regimes (regime filter from regime.py).
* Stop distance expressed in ATR multiples so sizing stays volatility-aware.
"""

from __future__ import annotations

from trading_bot.strategies.base_strategy import BaseStrategy


class MeanReversion(BaseStrategy):
    name = "mean_reversion"

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "MeanReversion is scheduled for Phase 7 (baseline strategies). "
            "It has not been implemented or tested; no results exist."
        )

    @property
    def warmup_bars(self) -> int:  # pragma: no cover
        raise NotImplementedError

    def on_bar(self, bar):  # pragma: no cover
        raise NotImplementedError
