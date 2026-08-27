"""Volatility-contraction breakout (Pass 4, EXPLORATORY).

Hypothesis (old, simple, honest): ranges contract before they expand.
Enter in the direction of a price break out of a recent range, but ONLY when
realized volatility sits in the low tail of its own recent history (the
"squeeze"); time-exit after a fixed hold if nothing else closes the trade.

This is a different return source from plain momentum (which fires
constantly) and from the UTC-day opening range: the trigger is conditional
on the volatility STATE, so trades are rare by construction — which also
keeps cost drag low.

EXPLORATORY: not part of any frozen candidate; subject to the full
four-round control battery like everything else. No claim of profitability
is made or implied.
"""

from __future__ import annotations

import math
from collections import deque

from trading_bot.core.events import Bar, Signal
from trading_bot.core.types import Side
from trading_bot.strategies.base_strategy import BaseStrategy


class VolatilityBreakout(BaseStrategy):
    name = "vol_breakout"

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        p = self.params
        if not (0 < float(p["squeeze_pctile"]) < 1):
            raise ValueError("squeeze_pctile must be in (0, 1)")
        for key in ("vol_window", "rank_window", "break_window", "hold_bars"):
            if int(p[key]) < 2:
                raise ValueError(f"{key} must be >= 2")
        self._closes: deque[float] = deque(maxlen=int(p["vol_window"]) + 1)
        self._vols: deque[float] = deque(maxlen=int(p["rank_window"]))
        self._highs: deque[float] = deque(maxlen=int(p["break_window"]))
        self._lows: deque[float] = deque(maxlen=int(p["break_window"]))
        self._hold_left: int | None = None

    @classmethod
    def default_params(cls) -> dict:
        return {
            "vol_window": 48,       # bars of realized volatility
            "rank_window": 240,     # history the current vol is ranked against
            "squeeze_pctile": 0.3,  # vol must be in this low quantile to arm
            "break_window": 24,     # prior-range window for the breakout level
            "hold_bars": 24,        # time exit after entry signal
        }

    @property
    def warmup_bars(self) -> int:
        p = self.params
        return int(p["vol_window"]) + int(p["rank_window"])

    def on_bar(self, bar: Bar) -> Signal | None:
        p = self.params
        # Breakout levels AND the squeeze state use STRICTLY PRIOR bars: the
        # breakout bar's own volatility expansion must not veto the very
        # signal the squeeze is meant to arm.
        prior_high = max(self._highs) if len(self._highs) == self._highs.maxlen else None
        prior_low = min(self._lows) if len(self._lows) == self._lows.maxlen else None

        signal: Signal | None = None
        if len(self._vols) == self._vols.maxlen and prior_high is not None:
            prior_vol = self._vols[-1]           # vol as of the PREVIOUS bar
            rank = sum(1 for v in self._vols if v <= prior_vol) / len(self._vols)
            squeezed = rank <= float(p["squeeze_pctile"])
            if squeezed and bar.close > prior_high:
                self._hold_left = int(p["hold_bars"])
                signal = Signal(ts=bar.ts, market_id=bar.market_id, direction=Side.LONG,
                                strength=rank,
                                reason=f"squeeze(vol pct {rank:.2f}) break above {prior_high:.2f}")
            elif squeezed and bar.close < prior_low:
                self._hold_left = int(p["hold_bars"])
                signal = Signal(ts=bar.ts, market_id=bar.market_id, direction=Side.SHORT,
                                strength=rank,
                                reason=f"squeeze(vol pct {rank:.2f}) break below {prior_low:.2f}")

        if signal is None and self._hold_left is not None:
            self._hold_left -= 1
            if self._hold_left <= 0:
                self._hold_left = None
                signal = Signal(ts=bar.ts, market_id=bar.market_id, direction=Side.FLAT,
                                reason="squeeze-trade time exit")

        # ---- state updates with the completed bar (after signal logic) ------
        self._closes.append(bar.close)
        if len(self._closes) == self._closes.maxlen:
            closes = list(self._closes)
            rets = [math.log(b / a) for a, b in zip(closes, closes[1:]) if a > 0]
            if rets:
                mean = sum(rets) / len(rets)
                self._vols.append(
                    math.sqrt(sum((r - mean) ** 2 for r in rets) / len(rets))
                )
        self._highs.append(bar.high)
        self._lows.append(bar.low)
        return signal

    def reset(self) -> None:
        self._closes.clear()
        self._vols.clear()
        self._highs.clear()
        self._lows.clear()
        self._hold_left = None
