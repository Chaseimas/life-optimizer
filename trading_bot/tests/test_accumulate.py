"""Data accumulation: append-only merges, immutable history, anomaly
detection, and the contamination proof (new fetches cannot alter data that
completed experiments used)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.data_pipeline.accumulate import accumulate_candles
from trading_bot.data_pipeline.store import BarStore

T0 = pd.Timestamp("2026-08-01 00:00", tz="UTC")
H = pd.Timedelta(hours=1)


def frame(start: pd.Timestamp, n: int, price0: float = 100.0, step_hours: float = 1.0):
    idx = pd.DatetimeIndex([start + H * step_hours * (i + 1) for i in range(n)], name="ts")
    # Prices derive from the TIMESTAMP so overlapping fetches agree by
    # construction (a real API serves the same bar for the same time).
    closes = price0 + ((idx - T0) / H).astype(float)
    return pd.DataFrame(
        {"open": closes - 0.5, "high": closes + 1.0, "low": closes - 1.0,
         "close": closes, "volume": 10.0},
        index=idx,
    )


@pytest.fixture()
def store(tmp_path):
    return BarStore(tmp_path / "raw", tmp_path / "processed")


def fetcher_for(df):
    def fetch(coin, interval, start, end):
        return df
    return fetch


def test_initial_accumulation(store):
    rep = accumulate_candles(store, "HL:ETH", "ETH", "1h", days=10,
                             fetch_fn=fetcher_for(frame(T0, 48)))
    assert rep.prior_rows == 0 and rep.new_rows == 48 and rep.total_rows == 48
    assert store.load("HL:ETH", "1h", stage="raw", source="hyperliquid_api").shape[0] == 48
    meta = store.meta("HL:ETH", "1h", stage="raw", source="hyperliquid_api")
    assert len(meta["fetch_history"]) == 1
    assert meta["fetch_history"][0]["new_rows"] == 48


def test_second_fetch_appends_only_new_rows(store):
    accumulate_candles(store, "HL:ETH", "ETH", "1h", days=10,
                       fetch_fn=fetcher_for(frame(T0, 48)))
    # Second fetch: overlaps the last 24 bars, adds 24 new ones.
    rep = accumulate_candles(store, "HL:ETH", "ETH", "1h", days=10,
                             fetch_fn=fetcher_for(frame(T0 + H * 24, 48)))
    assert rep.prior_rows == 48
    assert rep.overlap_rows == 24
    assert rep.new_rows == 24
    assert rep.total_rows == 72
    assert rep.overlap_mismatches == 0
    meta = store.meta("HL:ETH", "1h", stage="raw", source="hyperliquid_api")
    assert len(meta["fetch_history"]) == 2


def test_history_is_immutable_even_when_api_revises_it(store):
    """THE contamination proof: a later fetch returning DIFFERENT values for
    already-stored bars must not change one stored byte — it is detected and
    reported instead. Data that completed experiments used stays what it was."""
    original = frame(T0, 48)
    accumulate_candles(store, "HL:ETH", "ETH", "1h", days=10,
                       fetch_fn=fetcher_for(original))
    before = store.load("HL:ETH", "1h", stage="raw", source="hyperliquid_api")

    revised = frame(T0, 72)
    revised.iloc[:48, revised.columns.get_loc("close")] += 5.0   # API "revises" history
    rep = accumulate_candles(store, "HL:ETH", "ETH", "1h", days=10,
                             fetch_fn=fetcher_for(revised))
    assert rep.overlap_mismatches == 48
    assert len(rep.mismatch_samples) > 0

    after = store.load("HL:ETH", "1h", stage="raw", source="hyperliquid_api")
    pd.testing.assert_frame_equal(after.iloc[:48], before)       # old rows untouched
    assert after["close"].iloc[48] == revised["close"].iloc[48]  # new rows appended
    # Processed data before the boundary is likewise regenerated from the
    # UNCHANGED raw history:
    processed = store.load("HL:ETH", "1h", stage="processed")
    assert processed.loc[before.index, "close"].equals(before["close"])


def test_gap_and_grid_anomalies_detected(store):
    df = frame(T0, 30)
    df = df.drop(df.index[10:13])                                # 3 missing bars
    misaligned = frame(T0 + pd.Timedelta(minutes=7), 1)          # off the hour grid
    combined = pd.concat([df, misaligned]).sort_index()
    rep = accumulate_candles(store, "HL:ETH", "ETH", "1h", days=10,
                             fetch_fn=fetcher_for(combined))
    assert rep.gaps >= 1
    assert rep.missing_bars >= 3
    assert rep.off_grid_rows == 1


def test_funding_merge_is_immutable(store):
    idx1 = pd.date_range(T0, periods=24, freq="1h", tz="UTC")
    f1 = pd.Series(np.full(24, 1e-4), index=idx1)
    idx2 = pd.date_range(T0 + H * 12, periods=24, freq="1h", tz="UTC")
    f2 = pd.Series(np.full(24, 9e-4), index=idx2)                # overlap disagrees

    rep = accumulate_candles(
        store, "HL:ETH", "ETH", "1h", days=10,
        fetch_fn=fetcher_for(frame(T0, 24)),
        funding_fetch_fn=lambda coin, s, e: f1,
    )
    assert rep.funding_new_rows == 24
    rep2 = accumulate_candles(
        store, "HL:ETH", "ETH", "1h", days=10,
        fetch_fn=fetcher_for(frame(T0, 24)),
        funding_fetch_fn=lambda coin, s, e: f2,
    )
    assert rep2.funding_new_rows == 12                           # only the new half
    assert rep2.funding_mismatches == 12                         # disagreement detected
    merged = store.load_funding("HL:ETH")
    assert merged.loc[idx1].eq(1e-4).all()                       # old values kept


def test_no_data_at_all_raises(store):
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"],
                         index=pd.DatetimeIndex([], tz="UTC", name="ts"))
    with pytest.raises(ValueError, match="no data"):
        accumulate_candles(store, "HL:ETH", "ETH", "1h", days=10,
                           fetch_fn=fetcher_for(empty))
