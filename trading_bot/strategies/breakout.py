"""Opening-range / high-low breakout strategy.

STATUS: not implemented — Phase 7 (baseline strategies).

Planned design:
* Opening range defined from the first N minutes of the session (MNQ) or a
  fixed UTC window (perps); breakout entries beyond the range with
  volatility-scaled stops.
* Range boundaries computed strictly from completed bars; the breakout bar
  itself triggers at the NEXT bar's open (no intrabar fantasy fills before
  Phase 5's execution model exists).
* Must be studied alongside time-of-day effects — breakouts are notoriously
  session-dependent.
"""

from __future__ import annotations

from trading_bot.strategies.base_strategy import BaseStrategy


class OpeningRangeBreakout(BaseStrategy):
    name = "opening_range_breakout"

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "OpeningRangeBreakout is scheduled for Phase 7 (baseline strategies). "
            "It has not been implemented or tested; no results exist."
        )

    @property
    def warmup_bars(self) -> int:  # pragma: no cover
        raise NotImplementedError

    def on_bar(self, bar):  # pragma: no cover
        raise NotImplementedError
