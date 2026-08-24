"""Canonical bar-frame format and converters.

One format for every layer:

* index: tz-aware UTC ``DatetimeIndex`` named ``ts`` = bar CLOSE time
  (matches ``Bar.ts`` semantics: everything in the row was known at ``ts``).
* columns: ``open, high, low, close, volume`` as float64.
* strictly increasing index, no duplicates.

``ensure_canonical`` coerces/validates; ``frame_to_bars``/``bars_to_frame``
bridge to the event objects the strategies consume.
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from trading_bot.core.events import Bar

REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]

# Supported bar intervals -> seconds
INTERVALS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


class DataError(ValueError):
    pass


def interval_to_timedelta(interval: str) -> timedelta:
    try:
        return timedelta(seconds=INTERVALS[interval])
    except KeyError:
        raise DataError(
            f"Unsupported interval {interval!r}. Supported: {sorted(INTERVALS)}"
        ) from None


def ensure_canonical(df: pd.DataFrame, *, already_sorted: bool = False) -> pd.DataFrame:
    """Coerce a frame into canonical form; raise ``DataError`` if impossible.

    Does NOT clean data (that is clean.py's job) — it only guarantees shape:
    UTC tz-aware sorted unique index and float64 OHLCV columns.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DataError(f"missing required columns: {missing}")

    out = df[REQUIRED_COLUMNS].copy()

    if not isinstance(out.index, pd.DatetimeIndex):
        raise DataError("index must be a DatetimeIndex of bar close times")
    if out.index.tz is None:
        raise DataError(
            "index must be timezone-aware. Localize explicitly at ingestion "
            "time — guessing timezones is how session bugs are born."
        )
    out.index = out.index.tz_convert("UTC")
    out.index.name = "ts"

    for col in REQUIRED_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="raise").astype("float64")

    if not already_sorted:
        out = out.sort_index()
    if out.index.has_duplicates:
        # Shape guarantee only: keep the LAST record for a timestamp (a
        # venue's amended/final bar); clean.py reports duplicate counts.
        out = out[~out.index.duplicated(keep="last")]
    return out


def bars_to_frame(bars: list[Bar]) -> pd.DataFrame:
    if not bars:
        raise DataError("no bars to convert")
    df = pd.DataFrame(
        {
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume for b in bars],
        },
        index=pd.DatetimeIndex([b.ts for b in bars], name="ts"),
    )
    return ensure_canonical(df)


def frame_to_bars(df: pd.DataFrame, market_id: str) -> list[Bar]:
    df = ensure_canonical(df)
    return [
        Bar(
            ts=ts.to_pydatetime(),
            market_id=market_id,
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
        )
        for ts, row in zip(df.index, df.itertuples(index=False))
    ]
