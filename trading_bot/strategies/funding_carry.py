"""Funding-rate carry (Pass 4, EXPLORATORY).

A genuinely different return source from all price-based families: perpetual
FUNDING. When trailing funding is extreme relative to its own recent history
(crowded positioning paying heavily to hold), take the other side and
collect the carry; stand aside when funding is unremarkable.

* SHORT when trailing funding ranks in the top tail (longs pay heavily —
  the short collects funding and fades crowding).
* LONG when trailing funding ranks in the bottom tail.
* FLAT in a neutral band around the median; otherwise hold.

Holding periods are days, so the trade count is low and cost drag small —
the cost profile most likely to survive, per Pass-2's central finding.

Timestamp safety: the strategy receives the funding-rate SERIES at
construction and, on each bar, reads only entries with timestamp <= the
bar's close (binary search); rolling means are computed left-aligned so
position i uses entries <= i only. Verified by the truncation-invariance
test like every other strategy.

EXPLORATORY: no claim of profitability is made or implied. Not part of any
frozen candidate. Not in the CLI strategy registry (it requires a funding
series, which the registry cannot supply) — research code constructs it
directly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_bot.core.events import Bar, Signal
from trading_bot.core.types import Side
from trading_bot.strategies.base_strategy import BaseStrategy


class FundingCarry(BaseStrategy):
    name = "funding_carry"

    def __init__(self, params: dict | None = None, *, funding: pd.Series):
        super().__init__(params)
        p = self.params
        if not (0.5 < float(p["entry_pctile"]) < 1.0):
            raise ValueError("entry_pctile must be in (0.5, 1)")
        if not (0.0 <= float(p["neutral_band"]) < 0.5):
            raise ValueError("neutral_band must be in [0, 0.5)")
        if funding.index.tz is None:
            raise ValueError("funding series index must be tz-aware")
        f = funding.sort_index()
        # numpy datetime64 cannot carry a timezone: store naive-UTC stamps.
        self._f_ts = f.index.tz_convert("UTC").tz_localize(None).to_numpy()
        lb = int(p["lookback_hours"])
        # Left-aligned rolling mean: value at i uses entries (i-lb, i] only.
        self._trail = f.rolling(lb, min_periods=lb).mean().to_numpy()
        self._rank_window = int(p["rank_window_hours"])

    @classmethod
    def default_params(cls) -> dict:
        return {
            "lookback_hours": 24,      # trailing funding average
            "rank_window_hours": 720,  # ~30 days of history to rank against
            "entry_pctile": 0.85,      # enter beyond this extreme
            "neutral_band": 0.10,      # flat when |pct - 0.5| <= band
        }

    @property
    def warmup_bars(self) -> int:
        return 2  # readiness is governed by funding history, checked per bar

    def on_bar(self, bar: Bar) -> Signal | None:
        from datetime import timezone as _tz

        ts64 = np.datetime64(bar.ts.astimezone(_tz.utc).replace(tzinfo=None))
        idx = int(np.searchsorted(self._f_ts, ts64, side="right"))
        if idx < self._rank_window:
            return None
        current = self._trail[idx - 1]
        window = self._trail[idx - self._rank_window: idx]
        window = window[~np.isnan(window)]
        if np.isnan(current) or len(window) < self._rank_window // 2:
            return None
        pct = float((window <= current).mean())

        entry = float(self.params["entry_pctile"])
        band = float(self.params["neutral_band"])
        if pct >= entry:
            direction = Side.SHORT      # crowded longs pay; collect the carry
        elif pct <= 1.0 - entry:
            direction = Side.LONG
        elif abs(pct - 0.5) <= band:
            direction = Side.FLAT
        else:
            return None                 # in between: hold whatever is on

        return Signal(
            ts=bar.ts, market_id=bar.market_id, direction=direction,
            strength=abs(pct - 0.5) * 2,
            reason=f"trailing funding pct {pct:.2f} "
                   f"({current:+.5%}/h over {self.params['lookback_hours']}h)",
        )

    def reset(self) -> None:
        pass  # all state is precomputed and lookup-based; nothing to clear
