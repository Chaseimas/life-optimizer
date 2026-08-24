"""Canonical frame format: validation, conversion, interval handling."""

from __future__ import annotations

import pandas as pd
import pytest

from trading_bot.data_pipeline.frames import (
    DataError,
    bars_to_frame,
    ensure_canonical,
    frame_to_bars,
    interval_to_timedelta,
)
from trading_bot.tests.conftest import make_bars


def _frame(index):
    return pd.DataFrame(
        {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0}, index=index
    )


def test_naive_index_rejected():
    idx = pd.date_range("2024-01-01", periods=3, freq="5min")  # naive
    with pytest.raises(DataError, match="timezone-aware"):
        ensure_canonical(_frame(idx))


def test_non_datetime_index_rejected():
    with pytest.raises(DataError, match="DatetimeIndex"):
        ensure_canonical(_frame(pd.RangeIndex(3)))


def test_missing_columns_rejected():
    idx = pd.date_range("2024-01-01", periods=3, freq="5min", tz="UTC")
    df = _frame(idx).drop(columns=["volume"])
    with pytest.raises(DataError, match="volume"):
        ensure_canonical(df)


def test_converts_to_utc_and_sorts():
    idx = pd.DatetimeIndex(
        ["2024-01-01 12:00", "2024-01-01 11:00"], tz="America/Chicago"
    )
    out = ensure_canonical(_frame(idx))
    assert str(out.index.tz) == "UTC"
    assert out.index.is_monotonic_increasing
    assert out.index.name == "ts"


def test_duplicate_timestamps_keep_last():
    idx = pd.DatetimeIndex(["2024-01-01 12:00"] * 2, tz="UTC")
    df = _frame(idx)
    df.iloc[1, df.columns.get_loc("close")] = 9.9
    out = ensure_canonical(df)
    assert len(out) == 1
    assert out["close"].iloc[0] == 9.9


def test_bars_roundtrip():
    bars = make_bars([100, 101, 102, 103], market_id="RT")
    df = bars_to_frame(bars)
    back = frame_to_bars(df, "RT")
    assert back == bars


def test_interval_helper():
    assert interval_to_timedelta("1h").total_seconds() == 3600
    with pytest.raises(DataError, match="Unsupported interval"):
        interval_to_timedelta("7m")
