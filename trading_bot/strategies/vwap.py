"""VWAP-based strategy (distance-from-VWAP behavior).

STATUS: not implemented — Phase 7 (baseline strategies).

Planned design:
* Session-anchored VWAP computed incrementally from completed bars only
  (never from the forming bar — that would be look-ahead).
* Study both fade (revert to VWAP) and trend (hold beyond VWAP) variants;
  let the data pick, per market and per regime.
* For MNQ the VWAP anchor resets at the session open; for 24/7 perps use a
  rolling or UTC-day anchor — this is a research question, not an assumption.
"""

from __future__ import annotations

from trading_bot.strategies.base_strategy import BaseStrategy


class VWAPStrategy(BaseStrategy):
    name = "vwap"

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "VWAPStrategy is scheduled for Phase 7 (baseline strategies). "
            "It has not been implemented or tested; no results exist."
        )

    @property
    def warmup_bars(self) -> int:  # pragma: no cover
        raise NotImplementedError

    def on_bar(self, bar):  # pragma: no cover
        raise NotImplementedError
