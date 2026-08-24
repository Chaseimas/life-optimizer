"""Trend-regime classification and regime-gated momentum (Phase 7).

``EfficiencyRatioTracker``: Kaufman efficiency ratio computed incrementally
— |net move over N bars| / path length over N bars. Near 1: clean trend;
near 0: churn. Strictly causal (uses only completed bars).

``RegimeGatedMomentum``: SimpleMomentum whose signals only pass when the
market is actually trending (ER >= er_min); in churn it goes flat instead.
This is the baseline-vs-filter comparison the research philosophy demands:
run momentum with and without the gate on the same data — the gate must earn
its keep out-of-sample or be dropped. No claim of profitability is made.
"""

from __future__ import annotations

from collections import deque

from trading_bot.core.events import Bar, Signal
from trading_bot.core.types import Side
from trading_bot.strategies.base_strategy import BaseStrategy
from trading_bot.strategies.momentum import SimpleMomentum


class EfficiencyRatioTracker:
    """Incremental Kaufman efficiency ratio over ``window`` bars."""

    def __init__(self, window: int):
        if window < 2:
            raise ValueError("window must be >= 2")
        self.window = window
        self._closes: deque[float] = deque(maxlen=window + 1)

    def update(self, close: float) -> float | None:
        self._closes.append(close)
        if len(self._closes) < self._closes.maxlen:
            return None
        closes = list(self._closes)
        net = abs(closes[-1] - closes[0])
        path = sum(abs(b - a) for a, b in zip(closes, closes[1:]))
        if path <= 0:
            return 0.0
        return net / path

    def reset(self) -> None:
        self._closes.clear()


class RegimeGatedMomentum(BaseStrategy):
    name = "regime_gated_momentum"

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        if not (0.0 <= float(self.params["er_min"]) <= 1.0):
            raise ValueError("er_min must be in [0, 1]")
        self._momentum = SimpleMomentum(
            {"lookback": self.params["lookback"], "threshold": self.params["threshold"]}
        )
        self._er = EfficiencyRatioTracker(int(self.params["er_window"]))

    @classmethod
    def default_params(cls) -> dict:
        return {
            "lookback": 20,    # momentum window (as in SimpleMomentum)
            "threshold": 0.0,
            "er_window": 20,   # efficiency-ratio window
            "er_min": 0.3,     # required trendiness to act on momentum
        }

    @property
    def warmup_bars(self) -> int:
        return max(self._momentum.warmup_bars, int(self.params["er_window"]) + 1)

    def on_bar(self, bar: Bar) -> Signal | None:
        sig = self._momentum.on_bar(bar)
        er = self._er.update(bar.close)
        if sig is None or er is None:
            return None
        if er >= float(self.params["er_min"]):
            return Signal(
                ts=sig.ts, market_id=sig.market_id, direction=sig.direction,
                strength=sig.strength, reason=f"{sig.reason} | ER={er:.2f} (trending)",
            )
        # Churn regime: momentum has no standing -> be flat, don't hold hope.
        return Signal(
            ts=bar.ts, market_id=bar.market_id, direction=Side.FLAT,
            strength=0.0, reason=f"ER={er:.2f} < {self.params['er_min']} (churn)",
        )

    def reset(self) -> None:
        self._momentum.reset()
        self._er.reset()
