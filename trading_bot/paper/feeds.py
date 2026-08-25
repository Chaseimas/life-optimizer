"""Bar feeds for paper trading (Phase 13).

A feed yields COMPLETED bars in chronological order — the same objects the
backtester consumes, so the engine cannot tell replay from live data.

* ``ReplayFeed``: streams a stored dataset (works everywhere; also the
  equivalence-test harness proving paper == backtest on identical bars).
* ``HyperliquidPollingFeed``: polls the public candle endpoint and yields
  only bars whose close time has passed — the forming candle is never
  emitted (acting on a forming bar is intrabar peeking). Detects staleness
  and raises ``StaleFeedError`` so the trader can trip the kill switch.

No feed places orders. Nothing in the paper layer can.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Callable, Iterator

import pandas as pd

from trading_bot.core.events import Bar
from trading_bot.data_pipeline.frames import INTERVALS, frame_to_bars
from trading_bot.monitoring.logging import get_logger

log = get_logger("paper.feed")


class StaleFeedError(RuntimeError):
    """The feed stopped producing bars — treat as a data-feed failure."""


class BarFeed(ABC):
    @abstractmethod
    def stream(self) -> Iterator[Bar]:
        """Yield completed bars in strict chronological order."""


class ReplayFeed(BarFeed):
    def __init__(self, df: pd.DataFrame, market_id: str):
        self._bars = frame_to_bars(df, market_id)

    def stream(self) -> Iterator[Bar]:
        yield from self._bars

    def __len__(self) -> int:
        return len(self._bars)


class HyperliquidPollingFeed(BarFeed):
    """Poll Hyperliquid public candles; yield new COMPLETED bars only.

    Injectable clock/fetch/sleep so the logic is fully unit-testable without
    a network or real time. On a real machine the defaults just work.
    """

    def __init__(
        self,
        coin: str,
        interval: str,
        market_id: str,
        *,
        warmup_bars: int = 300,
        poll_seconds: float | None = None,
        stale_intervals: float = 3.0,
        max_polls: int | None = None,
        fetch_fn: Callable | None = None,
        now_fn: Callable[[], datetime] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        if interval not in INTERVALS:
            raise ValueError(f"unsupported interval {interval!r}")
        self.coin = coin
        self.interval = interval
        self.market_id = market_id
        self.warmup_bars = warmup_bars
        self.interval_seconds = INTERVALS[interval]
        self.poll_seconds = poll_seconds or max(10.0, self.interval_seconds / 6)
        self.stale_after = pd.Timedelta(seconds=stale_intervals * self.interval_seconds)
        self.max_polls = max_polls
        if fetch_fn is None:
            from trading_bot.data_pipeline.hyperliquid import fetch_candles
            fetch_fn = fetch_candles
        self._fetch = fetch_fn
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        self._sleep = sleep_fn

    def stream(self) -> Iterator[Bar]:
        last_ts: pd.Timestamp | None = None
        polls = 0
        while self.max_polls is None or polls < self.max_polls:
            now = pd.Timestamp(self._now())
            lookback = pd.Timedelta(seconds=self.interval_seconds * (self.warmup_bars + 2))
            df = self._fetch(self.coin, self.interval, now - lookback, now)
            # Completed bars only: close time must have passed. The venue also
            # returns the still-forming candle — it is NOT data yet.
            completed = df[df.index <= now]
            fresh = completed if last_ts is None else completed[completed.index > last_ts]
            for bar in frame_to_bars(fresh, self.market_id):
                yield bar
            if len(completed):
                last_ts = completed.index[-1]
            if last_ts is not None and now - last_ts > self.stale_after:
                raise StaleFeedError(
                    f"no completed {self.interval} bar for {self.coin} since "
                    f"{last_ts} (now {now}) — feed is stale"
                )
            polls += 1
            if self.max_polls is None or polls < self.max_polls:
                self._sleep(self.poll_seconds)
