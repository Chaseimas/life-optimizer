"""Opening-range breakout baseline (Phase 7).

Each day (UTC): build the high/low range from the bars closing within the
first ``range_minutes`` after ``range_start_hour``; afterwards, go long on a
close above the range high (short below the range low), at most one entry
per direction per day, and go flat at ``flat_hour``.

UTC-day based so it runs on 24/7 perps as-is. For MNQ the interesting anchor
is the session open in exchange time — that session-aware variant comes with
CME session research; time-of-day effects are exactly what Phase 7+ must
measure, not assume. No claim of profitability is made or implied.
"""

from __future__ import annotations

from datetime import date, timezone

from trading_bot.core.events import Bar, Signal
from trading_bot.core.types import Side
from trading_bot.strategies.base_strategy import BaseStrategy


class OpeningRangeBreakout(BaseStrategy):
    name = "opening_range_breakout"

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        if not (0 <= int(self.params["range_start_hour"]) <= 23):
            raise ValueError("range_start_hour must be 0..23")
        if int(self.params["range_minutes"]) < 5:
            raise ValueError("range_minutes must be >= 5")
        if not (0 <= int(self.params["flat_hour"]) <= 23):
            raise ValueError("flat_hour must be 0..23")
        self._day: date | None = None
        self._range_high: float | None = None
        self._range_low: float | None = None
        self._range_bars = 0
        self._traded_long = False
        self._traded_short = False

    @classmethod
    def default_params(cls) -> dict:
        return {
            "range_start_hour": 0,   # UTC hour the opening range starts
            "range_minutes": 60,     # length of the range window
            "buffer_frac": 0.0,      # extra breakout margin, fraction of range width
            "flat_hour": 23,         # UTC hour to be flat (day exit)
        }

    @property
    def warmup_bars(self) -> int:
        return 1  # per-day state; the first day's range builds internally

    def _reset_day(self, day: date) -> None:
        self._day = day
        self._range_high = None
        self._range_low = None
        self._range_bars = 0
        self._traded_long = False
        self._traded_short = False

    def on_bar(self, bar: Bar) -> Signal | None:
        ts = bar.ts.astimezone(timezone.utc)
        if self._day != ts.date():
            self._reset_day(ts.date())

        start_min = int(self.params["range_start_hour"]) * 60
        minutes = ts.hour * 60 + ts.minute
        in_range_window = start_min < minutes <= start_min + int(self.params["range_minutes"])

        if in_range_window:
            self._range_high = bar.high if self._range_high is None else max(self._range_high, bar.high)
            self._range_low = bar.low if self._range_low is None else min(self._range_low, bar.low)
            self._range_bars += 1
            return None

        if self._range_high is None or minutes <= start_min:
            return None  # before/without a range today

        if ts.hour >= int(self.params["flat_hour"]):
            return Signal(ts=bar.ts, market_id=bar.market_id, direction=Side.FLAT,
                          reason="day exit")

        width = self._range_high - self._range_low
        buffer = float(self.params["buffer_frac"]) * width
        if bar.close > self._range_high + buffer and not self._traded_long:
            self._traded_long = True
            return Signal(
                ts=bar.ts, market_id=bar.market_id, direction=Side.LONG,
                strength=(bar.close - self._range_high) / width if width > 0 else 0.0,
                reason=f"break above OR high {self._range_high:.2f} ({self._range_bars} range bars)",
            )
        if bar.close < self._range_low - buffer and not self._traded_short:
            self._traded_short = True
            return Signal(
                ts=bar.ts, market_id=bar.market_id, direction=Side.SHORT,
                strength=(self._range_low - bar.close) / width if width > 0 else 0.0,
                reason=f"break below OR low {self._range_low:.2f} ({self._range_bars} range bars)",
            )
        return None

    def reset(self) -> None:
        self._day = None
        self._range_high = None
        self._range_low = None
        self._range_bars = 0
        self._traded_long = False
        self._traded_short = False
