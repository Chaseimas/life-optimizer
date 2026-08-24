"""Event timestamp hygiene: naive datetimes are rejected everywhere."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trading_bot.core.events import Bar, Order, Signal
from trading_bot.core.types import Side

AWARE = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
NAIVE = datetime(2024, 1, 1, 12, 0)


def test_bar_rejects_naive_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        Bar(ts=NAIVE, market_id="MNQ", open=1, high=2, low=0.5, close=1.5, volume=10)


def test_signal_rejects_naive_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        Signal(ts=NAIVE, market_id="MNQ", direction=Side.LONG)


def test_order_rejects_naive_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        Order(ts=NAIVE, market_id="MNQ", side=Side.LONG, qty=1)


def test_bar_coherence_check():
    good = Bar(ts=AWARE, market_id="MNQ", open=100, high=110, low=95, close=105, volume=10)
    assert good.is_coherent()
    bad = Bar(ts=AWARE, market_id="MNQ", open=100, high=90, low=95, close=105, volume=10)
    assert not bad.is_coherent()
