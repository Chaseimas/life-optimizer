"""Hyperliquid data client: parsing and pagination against canned responses
(no network in tests, ever)."""

from __future__ import annotations

import pandas as pd
import pytest

from trading_bot.data_pipeline import hyperliquid as hl

H = 3_600_000  # one hour in ms
T0 = 1_700_000_000_000 - (1_700_000_000_000 % H)  # aligned hour boundary


def candle(open_ms: int, o=100.0, h=105.0, lo=95.0, c=102.0, v=10.0, coin="BTC", interval="1h"):
    return {
        "t": open_ms, "T": open_ms + H, "s": coin, "i": interval,
        "o": str(o), "h": str(h), "l": str(lo), "c": str(c), "v": str(v), "n": 5,
    }


def test_parse_candles_index_is_close_time():
    df = hl.parse_candles([candle(T0)], coin="BTC", interval="1h")
    assert len(df) == 1
    # 't' is the OPEN; the canonical index must be the CLOSE (t + 1h).
    assert df.index[0] == pd.Timestamp(T0 + H, unit="ms", tz="UTC")
    assert df["open"].iloc[0] == 100.0
    assert df["close"].iloc[0] == 102.0


def test_parse_candles_rejects_mixed_coins():
    with pytest.raises(hl.HyperliquidDataError, match="mixed"):
        hl.parse_candles(
            [candle(T0), candle(T0 + H, coin="ETH")], coin="BTC", interval="1h"
        )


def test_parse_candles_empty():
    df = hl.parse_candles([], coin="BTC", interval="1h")
    assert df.empty
    assert str(df.index.tz) == "UTC"


def test_parse_funding():
    raw = [
        {"coin": "BTC", "fundingRate": "0.0000125", "premium": "0.0001", "time": T0},
        {"coin": "BTC", "fundingRate": "-0.0000030", "premium": "0.0", "time": T0 + H},
    ]
    s = hl.parse_funding(raw, coin="BTC")
    assert len(s) == 2
    assert s.iloc[0] == pytest.approx(1.25e-5)
    assert s.iloc[1] == pytest.approx(-3.0e-6)
    assert str(s.index.tz) == "UTC"


def test_fetch_candles_paginates(monkeypatch):
    """Server returns full pages until exhausted; fetch must stitch them."""
    page_size = 3  # miniature MAX_CANDLES_PER_REQUEST for the test
    all_candles = [candle(T0 + i * H, o=100 + i) for i in range(7)]
    calls = []

    def fake_post(payload, **kwargs):
        calls.append(payload)
        start = payload["req"]["startTime"]
        remaining = [c for c in all_candles if c["t"] >= start]
        return remaining[:page_size]

    monkeypatch.setattr(hl, "_post", fake_post)
    monkeypatch.setattr(hl, "MAX_CANDLES_PER_REQUEST", page_size)

    start = pd.Timestamp(T0, unit="ms", tz="UTC")
    end = pd.Timestamp(T0 + 7 * H, unit="ms", tz="UTC")
    df = hl.fetch_candles("BTC", "1h", start, end)

    assert len(df) == 7
    assert len(calls) >= 3  # 3 + 3 + 1
    assert list(df["open"]) == [100 + i for i in range(7)]
    assert df.index.is_monotonic_increasing
    assert not df.index.has_duplicates


def test_fetch_candles_requires_tz():
    with pytest.raises(hl.HyperliquidDataError, match="tz-aware"):
        hl.fetch_candles("BTC", "1h", pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02"))
