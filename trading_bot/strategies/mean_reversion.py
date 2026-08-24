"""Z-score mean reversion baseline (Phase 7).

Fades extensions from a rolling mean, normalized by rolling standard
deviation: short when price is stretched ``entry_z`` sigmas above its mean,
long when stretched below, flat when it has reverted inside ``exit_z``.

Deliberately simple and transparent — a baseline to measure, not a product.
No claim of profitability is made or implied. Protective stops are the
engine's job (ATR-based via BacktestConfig).
"""

from __future__ import annotations

import math
from collections import deque

from trading_bot.core.events import Bar, Signal
from trading_bot.core.types import Side
from trading_bot.strategies.base_strategy import BaseStrategy


class ZScoreMeanReversion(BaseStrategy):
    name = "zscore_mean_reversion"

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        w = int(self.params["window"])
        if w < 5:
            raise ValueError("window must be >= 5")
        if not (0 <= float(self.params["exit_z"]) < float(self.params["entry_z"])):
            raise ValueError("need 0 <= exit_z < entry_z")
        self._closes: deque[float] = deque(maxlen=w)

    @classmethod
    def default_params(cls) -> dict:
        return {
            "window": 20,     # rolling window for mean/std
            "entry_z": 2.0,   # enter when |z| >= entry_z (fade the extension)
            "exit_z": 0.5,    # flatten when |z| <= exit_z (reverted)
        }

    @property
    def warmup_bars(self) -> int:
        return int(self.params["window"])

    def on_bar(self, bar: Bar) -> Signal | None:
        self._closes.append(bar.close)
        if len(self._closes) < self._closes.maxlen:
            return None
        n = len(self._closes)
        mean = sum(self._closes) / n
        var = sum((c - mean) ** 2 for c in self._closes) / n
        std = math.sqrt(var)
        if std <= 0:
            return None
        z = (bar.close - mean) / std

        entry_z = float(self.params["entry_z"])
        exit_z = float(self.params["exit_z"])
        if z >= entry_z:
            direction = Side.SHORT
        elif z <= -entry_z:
            direction = Side.LONG
        elif abs(z) <= exit_z:
            direction = Side.FLAT
        else:
            return None  # in between: hold whatever position exists

        return Signal(
            ts=bar.ts, market_id=bar.market_id, direction=direction,
            strength=abs(z), reason=f"z={z:+.2f} over {n} bars",
        )

    def reset(self) -> None:
        self._closes.clear()
