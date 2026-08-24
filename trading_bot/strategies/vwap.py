"""Rolling-VWAP distance baseline (Phase 7).

Trades the distance between price and a rolling volume-weighted average
price. Two modes — the data decides which (if either) has merit, per market:

* mode="fade":  price stretched above VWAP -> short (expect reversion);
                stretched below -> long; near VWAP -> flat.
* mode="trend": the same distances traded in the direction of the move.

Rolling (not session-anchored) so it works identically on 24/7 perps and
futures; a CME session-anchored variant belongs with session-aware research.
No claim of profitability is made or implied.
"""

from __future__ import annotations

from collections import deque

from trading_bot.core.events import Bar, Signal
from trading_bot.core.types import Side
from trading_bot.strategies.base_strategy import BaseStrategy


class RollingVWAPStrategy(BaseStrategy):
    name = "rolling_vwap"

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        if self.params["mode"] not in ("fade", "trend"):
            raise ValueError("mode must be 'fade' or 'trend'")
        if not (0 <= float(self.params["exit_dist"]) < float(self.params["entry_dist"])):
            raise ValueError("need 0 <= exit_dist < entry_dist")
        w = int(self.params["window"])
        if w < 5:
            raise ValueError("window must be >= 5")
        self._pv: deque[float] = deque(maxlen=w)
        self._vol: deque[float] = deque(maxlen=w)

    @classmethod
    def default_params(cls) -> dict:
        return {
            "window": 60,        # bars in the rolling VWAP
            "mode": "fade",
            "entry_dist": 0.005, # |close/vwap - 1| to enter (0.5%)
            "exit_dist": 0.001,  # flatten when back within 0.1%
        }

    @property
    def warmup_bars(self) -> int:
        return int(self.params["window"])

    def on_bar(self, bar: Bar) -> Signal | None:
        tp = (bar.high + bar.low + bar.close) / 3.0
        self._pv.append(tp * bar.volume)
        self._vol.append(bar.volume)
        if len(self._vol) < self._vol.maxlen:
            return None
        vol_sum = sum(self._vol)
        if vol_sum <= 0:
            return None
        vwap = sum(self._pv) / vol_sum
        if vwap <= 0:
            return None
        dist = bar.close / vwap - 1.0

        entry = float(self.params["entry_dist"])
        exit_ = float(self.params["exit_dist"])
        stretched = Side.SHORT if dist >= entry else Side.LONG if dist <= -entry else None
        if stretched is not None:
            direction = stretched if self.params["mode"] == "fade" else Side(-int(stretched))
        elif abs(dist) <= exit_:
            direction = Side.FLAT
        else:
            return None  # in between: hold

        return Signal(
            ts=bar.ts, market_id=bar.market_id, direction=direction,
            strength=abs(dist), reason=f"vwap dist {dist:+.3%} ({self.params['mode']})",
        )

    def reset(self) -> None:
        self._pv.clear()
        self._vol.clear()
