"""Simple time-series momentum.

The first baseline (Phase 7 candidate): direction of the trailing N-bar
return. Deliberately trivial — its job is to be an honest baseline, and in
Phase 1 to exercise the research pipeline end-to-end.

No claim of profitability is made or implied.
"""

from __future__ import annotations

from collections import deque

from trading_bot.core.events import Bar, Signal
from trading_bot.core.types import Side
from trading_bot.strategies.base_strategy import BaseStrategy


class SimpleMomentum(BaseStrategy):
    name = "simple_momentum"

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        lb = int(self.params["lookback"])
        if lb < 1:
            raise ValueError("lookback must be >= 1")
        self._closes: deque[float] = deque(maxlen=lb + 1)

    @classmethod
    def default_params(cls) -> dict:
        return {
            "lookback": 20,     # bars for the momentum window
            "threshold": 0.0,   # |trailing return| must exceed this to signal
        }

    @property
    def warmup_bars(self) -> int:
        return int(self.params["lookback"]) + 1

    def on_bar(self, bar: Bar) -> Signal | None:
        self._closes.append(bar.close)
        if len(self._closes) < self._closes.maxlen:
            return None  # still warming up

        oldest = self._closes[0]
        if oldest <= 0:
            return None
        momentum = self._closes[-1] / oldest - 1.0

        threshold = float(self.params["threshold"])
        if momentum > threshold:
            direction = Side.LONG
        elif momentum < -threshold:
            direction = Side.SHORT
        else:
            direction = Side.FLAT

        return Signal(
            ts=bar.ts,
            market_id=bar.market_id,
            direction=direction,
            strength=abs(momentum),
            reason=f"{self.params['lookback']}-bar momentum {momentum:+.4%}",
        )

    def reset(self) -> None:
        self._closes.clear()
