"""Generic CSV bar importer — the ingestion path for MNQ.

High-quality CME intraday data is commercial (e.g. Databento, or exports
from your futures broker); it arrives as CSV/DBN files, not from a free API.
This importer maps any reasonably-shaped OHLCV CSV into the canonical frame:

    import_csv("mnq_1m.csv", ColumnMap(ts="ts_event", tz="UTC",
               ts_semantics="open", interval="1m"))

Timestamp handling is explicit and strict:
* You must declare the timezone (or the timestamps must carry offsets).
* You must declare whether timestamps mark bar OPEN or CLOSE — the canonical
  index is CLOSE time, and silently guessing off-by-one-bar alignment is a
  classic source of look-ahead bias.
* Epoch timestamps auto-detect s/ms/us/ns by magnitude.

Databento OHLCV CSVs typically use ``ts_event`` (nanosecond epoch, UTC, bar
OPEN time) with lowercase ``open, high, low, close, volume`` — the defaults
here match that shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from trading_bot.data_pipeline.frames import (
    DataError,
    ensure_canonical,
    interval_to_timedelta,
)


@dataclass(frozen=True)
class ColumnMap:
    ts: str = "ts_event"
    open: str = "open"
    high: str = "high"
    low: str = "low"
    close: str = "close"
    volume: str = "volume"
    tz: str = "UTC"                  # timezone of naive timestamps; ignored if tz-aware/epoch
    ts_semantics: str = "open"       # "open" or "close": what the timestamp marks
    interval: str | None = None      # required when ts_semantics == "open"
    price_scale: float = 1.0         # e.g. 1e-9 for Databento fixed-point exports


def _parse_timestamps(col: pd.Series, tz: str) -> pd.DatetimeIndex:
    if pd.api.types.is_numeric_dtype(col):
        mag = float(col.dropna().abs().max())
        if mag > 1e17:
            unit = "ns"
        elif mag > 1e14:
            unit = "us"
        elif mag > 1e11:
            unit = "ms"
        else:
            unit = "s"
        idx = pd.DatetimeIndex(pd.to_datetime(col, unit=unit, utc=True))
    else:
        parsed = pd.to_datetime(col, errors="raise", format="mixed")
        idx = pd.DatetimeIndex(parsed)
        if idx.tz is None:
            idx = idx.tz_localize(tz)
        idx = idx.tz_convert("UTC")
    return idx


def import_csv(path: str | Path, colmap: ColumnMap = ColumnMap()) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise DataError(f"CSV not found: {path}")
    raw = pd.read_csv(path)

    needed = {colmap.ts, colmap.open, colmap.high, colmap.low, colmap.close, colmap.volume}
    missing = needed - set(raw.columns)
    if missing:
        raise DataError(
            f"CSV {path.name} is missing columns {sorted(missing)}. "
            f"Available: {list(raw.columns)}. Pass a ColumnMap that matches."
        )

    idx = _parse_timestamps(raw[colmap.ts], colmap.tz)
    if colmap.ts_semantics == "open":
        if not colmap.interval:
            raise DataError(
                "ts_semantics='open' requires the bar interval so timestamps "
                "can be shifted to CLOSE time (the canonical convention)."
            )
        idx = idx + interval_to_timedelta(colmap.interval)
    elif colmap.ts_semantics != "close":
        raise DataError("ts_semantics must be 'open' or 'close'")

    # .to_numpy(): building a DataFrame from Series against a NEW index would
    # align on the old RangeIndex and silently produce all-NaN columns.
    df = pd.DataFrame(
        {
            "open": pd.to_numeric(raw[colmap.open], errors="raise").to_numpy() * colmap.price_scale,
            "high": pd.to_numeric(raw[colmap.high], errors="raise").to_numpy() * colmap.price_scale,
            "low": pd.to_numeric(raw[colmap.low], errors="raise").to_numpy() * colmap.price_scale,
            "close": pd.to_numeric(raw[colmap.close], errors="raise").to_numpy() * colmap.price_scale,
            "volume": pd.to_numeric(raw[colmap.volume], errors="raise").to_numpy(),
        },
        index=idx,
    )
    df.index.name = "ts"
    return ensure_canonical(df)
