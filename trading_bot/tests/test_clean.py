"""Data cleaning: drops are counted, gaps reported (never filled), sessions
filtered in exchange-local time."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from trading_bot.data_pipeline.clean import clean_frame, filter_cme_session


def frame_from_closes(closes, start="2024-01-01", freq="5min", tz="UTC"):
    closes = np.asarray(closes, dtype=float)
    idx = pd.date_range(start, periods=len(closes), freq=freq, tz=tz)
    opens = np.concatenate([[closes[0]], closes[:-1]])
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) * 1.0005,
            "low": np.minimum(opens, closes) * 0.9995,
            "close": closes,
            "volume": np.full(len(closes), 1000.0),
        },
        index=idx,
    )


def test_clean_passthrough_on_good_data():
    df = frame_from_closes(100 + np.sin(np.arange(100)) * 0.1)
    out, rep = clean_frame(df, interval="5m")
    assert len(out) == 100
    assert rep.rows_in == 100 and rep.rows_out == 100
    assert rep.bad_ticks_dropped == 0
    assert rep.gap_count == 0


def test_nan_and_nonpositive_dropped():
    df = frame_from_closes([100.0] * 10)
    df.iloc[2, df.columns.get_loc("close")] = np.nan
    df.iloc[5, df.columns.get_loc("low")] = -1.0
    out, rep = clean_frame(df, interval="5m")
    assert rep.nan_dropped == 1
    assert rep.nonpositive_dropped == 1
    assert len(out) == 8


def test_incoherent_ohlc_dropped():
    df = frame_from_closes([100.0] * 10)
    df.iloc[3, df.columns.get_loc("high")] = 90.0  # high < low
    out, rep = clean_frame(df, interval="5m")
    assert rep.incoherent_dropped == 1
    assert len(out) == 9


def test_duplicates_counted():
    df = frame_from_closes([100.0] * 10)
    df = pd.concat([df, df.iloc[[4]]]).sort_index()
    out, rep = clean_frame(df, interval="5m")
    assert rep.duplicates_dropped == 1
    assert len(out) == 10


def test_bad_tick_dropped_but_real_move_kept():
    # Bad tick: spike to 130 immediately reverted.
    closes = [100.0] * 50 + [130.0] + [100.0] * 49
    out, rep = clean_frame(frame_from_closes(closes), interval="5m")
    assert rep.bad_ticks_dropped == 1
    assert 130.0 not in out["close"].values

    # Real move: jump to 130 that STAYS is data, not an error.
    closes2 = [100.0] * 50 + [130.0] * 50
    out2, rep2 = clean_frame(frame_from_closes(closes2), interval="5m")
    assert rep2.bad_ticks_dropped == 0
    assert rep2.extreme_moves_flagged >= 1
    assert 130.0 in out2["close"].values


def test_gaps_reported_not_filled():
    df = frame_from_closes([100.0] * 20, freq="1h")
    df = df.drop(df.index[10:13])  # 3 missing hourly bars
    out, rep = clean_frame(df, interval="1h")
    assert len(out) == 17            # nothing fabricated
    assert rep.gap_count == 1
    assert rep.gap_bars_missing == 3
    assert rep.largest_gap != ""


def test_cme_session_filter():
    stamps = [
        ("2024-01-10 15:00", True),   # Wed afternoon, in session
        ("2024-01-10 16:00", True),   # bar CLOSING at 16:00 CT is the last in-session bar
        ("2024-01-10 16:30", False),  # daily maintenance halt
        ("2024-01-10 17:00", False),  # bar closing exactly at the open boundary
        ("2024-01-10 17:05", True),   # evening session
        ("2024-01-12 18:00", False),  # Friday evening: closed for the week
        ("2024-01-13 12:00", False),  # Saturday
        ("2024-01-14 12:00", False),  # Sunday before the open
        ("2024-01-14 18:00", True),   # Sunday evening session
    ]
    idx = pd.DatetimeIndex([s for s, _ in stamps], tz="America/Chicago")
    df = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 10.0},
        index=idx,
    )
    out, rep = filter_cme_session(df)
    kept_ct = set(out.index.tz_convert("America/Chicago").strftime("%Y-%m-%d %H:%M"))
    for stamp, keep in stamps:
        assert (stamp in kept_ct) == keep, f"{stamp}: expected keep={keep}"
    assert rep.session_rows_dropped == sum(1 for _, k in stamps if not k)


def test_cme_holiday_filter():
    idx = pd.DatetimeIndex(["2024-01-10 15:00", "2024-01-11 15:00"], tz="America/Chicago")
    df = pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 10.0},
        index=idx,
    )
    out, _ = filter_cme_session(df, holidays=[date(2024, 1, 10)])
    assert len(out) == 1
    assert out.index.tz_convert("America/Chicago")[0].day == 11
