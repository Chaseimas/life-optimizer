"""MNQ pipeline groundwork: Databento-shaped import, tick validation, session
filtering, and the DST-aware session-anchored opening range."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.data_pipeline.mnq import (
    MNQ_COST_ASSUMPTIONS,
    count_off_tick,
    import_mnq_csv,
    rth_opening_range,
)
from trading_bot.data_pipeline.store import BarStore


def ns(ts: str) -> int:
    return int(pd.Timestamp(ts, tz="UTC").value)


@pytest.fixture()
def store(tmp_path):
    return BarStore(tmp_path / "raw", tmp_path / "processed")


def test_import_validates_and_session_filters(store, tmp_path):
    rows = [
        # ts_event = bar OPEN (ns, UTC), Databento convention; 15m bars.
        # Wed 2024-01-10 (CST): 14:30/14:45 UTC opens -> in-session closes.
        {"ts_event": ns("2024-01-10 14:30"), "open": 17000.25, "high": 17010.00,
         "low": 16995.50, "close": 17005.75, "volume": 500},
        {"ts_event": ns("2024-01-10 14:45"), "open": 17005.75, "high": 17012.25,
         "low": 17001.00, "close": 17010.00, "volume": 450},
        # Off-tick close (bad export precision) — must be counted. Kept
        # inside the bar's range so only tick validation flags it:
        {"ts_event": ns("2024-01-10 15:00"), "open": 17010.00, "high": 17015.00,
         "low": 17005.00, "close": 17008.13, "volume": 400},
        # Maintenance break: open 22:15 UTC -> close 22:30 UTC = 16:30 CT:
        {"ts_event": ns("2024-01-10 22:15"), "open": 17010.00, "high": 17011.00,
         "low": 17009.00, "close": 17010.50, "volume": 5},
        # Saturday: closed.
        {"ts_event": ns("2024-01-13 12:00"), "open": 17010.00, "high": 17011.00,
         "low": 17009.00, "close": 17010.25, "volume": 1},
    ]
    path = tmp_path / "mnq_15m.csv"
    pd.DataFrame(rows).to_csv(path, index=False)

    report = import_mnq_csv(store, path, interval="15m")
    assert report.rows_imported == 5
    assert report.off_tick_prices == 1
    assert report.session_rows_dropped == 2          # break bar + Saturday
    assert report.rows_processed == 3
    assert report.notes                              # off-tick note present

    raw = store.load("MNQ", "15m", stage="raw", source="csv:mnq_15m.csv")
    assert len(raw) == 5                             # raw kept untouched
    processed = store.load("MNQ", "15m", stage="processed")
    assert len(processed) == 3


def test_count_off_tick():
    idx = pd.DatetimeIndex(["2024-01-10 15:00"], tz="UTC")
    good = pd.DataFrame({"open": 17000.25, "high": 17000.50, "low": 17000.00,
                         "close": 17000.75, "volume": 1.0}, index=idx)
    assert count_off_tick(good) == 0
    bad = good.copy()
    bad["close"] = 17000.13
    assert count_off_tick(bad) == 1


def test_cost_assumptions_documented():
    assert MNQ_COST_ASSUMPTIONS["commission_per_side_usd"] > 0
    assert "VERIFY" in MNQ_COST_ASSUMPTIONS["verification_required"]


def _bar_frame(stamps_utc: list[str], base: float = 17000.0) -> pd.DataFrame:
    idx = pd.DatetimeIndex(stamps_utc, tz="UTC", name="ts")
    n = len(idx)
    return pd.DataFrame(
        {"open": base, "high": base + np.arange(1, n + 1, dtype=float),
         "low": base - np.arange(1, n + 1, dtype=float),
         "close": base, "volume": 100.0},
        index=idx,
    )


def test_rth_opening_range_is_dst_aware():
    """08:30 CT is 14:30 UTC in January (CST) but 13:30 UTC in July (CDT) —
    the anchor must follow the exchange clock, not a fixed UTC hour."""
    df = _bar_frame([
        # Jan 10 (CST): closes 14:45 and 15:00 UTC = 8:45 / 9:00 CT -> IN
        "2024-01-10 14:45", "2024-01-10 15:00",
        # 15:15 UTC = 9:15 CT -> outside the 30-minute range
        "2024-01-10 15:15",
        # Jul 10 (CDT): closes 13:45 and 14:00 UTC = 8:45 / 9:00 CT -> IN
        "2024-07-10 13:45", "2024-07-10 14:00",
        # 14:30 UTC = 9:30 CT -> outside
        "2024-07-10 14:30",
    ])
    out = rth_opening_range(df, range_minutes=30)
    assert len(out) == 2
    jan = out.loc[pd.Timestamp("2024-01-10").date()]
    jul = out.loc[pd.Timestamp("2024-07-10").date()]
    assert jan["n_bars"] == 2 and jul["n_bars"] == 2
    # Range built only from contributing bars (highs are base+1, base+2, ...):
    assert jan["range_high"] == pytest.approx(17002.0)
    assert jul["range_high"] == pytest.approx(17005.0)
    assert jan["range_end_ts"] == pd.Timestamp("2024-01-10 15:00", tz="UTC")
    assert jul["range_end_ts"] == pd.Timestamp("2024-07-10 14:00", tz="UTC")


def test_rth_opening_range_empty_when_no_session_bars():
    df = _bar_frame(["2024-01-10 03:00"])                # overnight only
    out = rth_opening_range(df, range_minutes=30)
    assert out.empty
