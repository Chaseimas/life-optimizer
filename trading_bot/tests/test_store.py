"""Bar storage: parquet round trips, metadata sidecars, catalog, funding."""

from __future__ import annotations

import pandas as pd
import pytest

from trading_bot.data_pipeline.frames import DataError
from trading_bot.data_pipeline.store import BarStore
from trading_bot.tests.conftest import make_bars
from trading_bot.data_pipeline.frames import bars_to_frame


@pytest.fixture()
def store(tmp_path):
    return BarStore(tmp_path / "raw", tmp_path / "processed")


@pytest.fixture()
def df():
    return bars_to_frame(make_bars([100, 101, 99, 102, 103], market_id="HL:BTC"))


def test_roundtrip_processed(store, df):
    store.save(df, market_id="HL:BTC", interval="5m", stage="processed", source="unit")
    loaded = store.load("HL:BTC", "5m", stage="processed")
    pd.testing.assert_frame_equal(loaded, df)
    assert str(loaded.index.tz) == "UTC"


def test_raw_and_processed_are_separate_files(store, df):
    p_raw = store.save(df, market_id="HL:BTC", interval="5m", stage="raw", source="api")
    p_proc = store.save(df, market_id="HL:BTC", interval="5m", stage="processed", source="api")
    assert p_raw != p_proc
    assert p_raw.exists() and p_proc.exists()


def test_meta_sidecar(store, df):
    store.save(df, market_id="HL:BTC", interval="5m", stage="processed", source="unit",
               notes="test dataset")
    meta = store.meta("HL:BTC", "5m", stage="processed")
    assert meta["rows"] == 5
    assert meta["market_id"] == "HL:BTC"
    assert meta["source"] == "unit"
    assert meta["notes"] == "test dataset"
    assert meta["start"] < meta["end"]


def test_catalog_lists_everything(store, df):
    store.save(df, market_id="HL:BTC", interval="5m", stage="raw", source="api")
    store.save(df, market_id="HL:BTC", interval="5m", stage="processed", source="api")
    cat = store.catalog()
    assert len(cat) == 2
    stages = {e["stage"] for e in cat}
    assert stages == {"raw", "processed"}


def test_load_missing_dataset_is_helpful(store):
    with pytest.raises(FileNotFoundError, match="fetch"):
        store.load("MNQ", "1m", stage="processed")


def test_refuses_empty_dataset(store, df):
    with pytest.raises(DataError, match="empty"):
        store.save(df.iloc[0:0], market_id="X", interval="5m", stage="processed", source="u")


def test_funding_roundtrip(store):
    idx = pd.date_range("2024-01-01", periods=5, freq="1h", tz="UTC")
    s = pd.Series([1e-4, -2e-5, 3e-5, 0.0, 1e-4], index=idx)
    store.save_funding(s, "HL:BTC")
    loaded = store.load_funding("HL:BTC")
    assert list(loaded.values) == list(s.values)
    assert loaded.index.tz is not None


def test_funding_requires_tz(store):
    s = pd.Series([1e-4], index=pd.DatetimeIndex(["2024-01-01"]))
    with pytest.raises(DataError, match="tz-aware"):
        store.save_funding(s, "HL:BTC")
