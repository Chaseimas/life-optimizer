"""CSV importer: timestamp semantics, timezone strictness, epoch detection."""

from __future__ import annotations

import pandas as pd
import pytest

from trading_bot.data_pipeline.csv_import import ColumnMap, import_csv
from trading_bot.data_pipeline.frames import DataError


def write_csv(tmp_path, df, name="bars.csv"):
    p = tmp_path / name
    df.to_csv(p, index=False)
    return p


BASE = pd.Timestamp("2024-01-02 09:30:00", tz="UTC")


def _ohlcv(n=3):
    return {
        "open": [100.0 + i for i in range(n)],
        "high": [101.0 + i for i in range(n)],
        "low": [99.0 + i for i in range(n)],
        "close": [100.5 + i for i in range(n)],
        "volume": [10 * (i + 1) for i in range(n)],
    }


def test_epoch_ns_open_semantics_shifts_to_close(tmp_path):
    ts_ns = [(BASE + pd.Timedelta(minutes=i)).value for i in range(3)]
    p = write_csv(tmp_path, pd.DataFrame({"ts_event": ts_ns, **_ohlcv()}))
    df = import_csv(p, ColumnMap(interval="1m", ts_semantics="open"))
    # bar opening 09:30 with 1m interval closes at 09:31
    assert df.index[0] == BASE + pd.Timedelta(minutes=1)
    assert len(df) == 3
    # values must survive the index rebuild (regression: NaN via index alignment)
    assert df["open"].tolist() == [100.0, 101.0, 102.0]
    assert df["volume"].tolist() == [10.0, 20.0, 30.0]


def test_epoch_seconds_autodetected(tmp_path):
    ts_s = [int((BASE + pd.Timedelta(minutes=i)).timestamp()) for i in range(3)]
    p = write_csv(tmp_path, pd.DataFrame({"ts_event": ts_s, **_ohlcv()}))
    df = import_csv(p, ColumnMap(interval="1m", ts_semantics="open"))
    assert df.index[0] == BASE + pd.Timedelta(minutes=1)


def test_close_semantics_no_shift(tmp_path):
    ts = [(BASE + pd.Timedelta(minutes=i)).isoformat() for i in range(3)]
    p = write_csv(tmp_path, pd.DataFrame({"ts_event": ts, **_ohlcv()}))
    df = import_csv(p, ColumnMap(ts_semantics="close"))
    assert df.index[0] == BASE


def test_naive_strings_localized_with_declared_tz(tmp_path):
    ts = ["2024-01-02 08:30:00", "2024-01-02 08:31:00", "2024-01-02 08:32:00"]
    p = write_csv(tmp_path, pd.DataFrame({"ts_event": ts, **_ohlcv()}))
    df = import_csv(p, ColumnMap(tz="America/Chicago", ts_semantics="close"))
    # 08:30 CST == 14:30 UTC
    assert df.index[0] == pd.Timestamp("2024-01-02 14:30:00", tz="UTC")


def test_open_semantics_requires_interval(tmp_path):
    ts = [(BASE + pd.Timedelta(minutes=i)).isoformat() for i in range(3)]
    p = write_csv(tmp_path, pd.DataFrame({"ts_event": ts, **_ohlcv()}))
    with pytest.raises(DataError, match="interval"):
        import_csv(p, ColumnMap(ts_semantics="open", interval=None))


def test_missing_column_lists_available(tmp_path):
    p = write_csv(tmp_path, pd.DataFrame({"time": [1], "o": [1], "h": [1], "l": [1],
                                          "c": [1], "vol": [1]}))
    with pytest.raises(DataError, match="missing columns"):
        import_csv(p, ColumnMap(interval="1m"))


def test_price_scale(tmp_path):
    ts_ns = [(BASE + pd.Timedelta(minutes=i)).value for i in range(3)]
    data = _ohlcv()
    scaled = {k: [v * 1e9 for v in vals] if k != "volume" else vals for k, vals in data.items()}
    p = write_csv(tmp_path, pd.DataFrame({"ts_event": ts_ns, **scaled}))
    df = import_csv(p, ColumnMap(interval="1m", price_scale=1e-9))
    assert df["open"].iloc[0] == pytest.approx(100.0)
    assert df["volume"].iloc[0] == 10
