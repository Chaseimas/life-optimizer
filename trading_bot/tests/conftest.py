"""Shared test fixtures. Ensures the repo root is importable regardless of
where pytest is invoked from."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from trading_bot.core.config import load_config
from trading_bot.core.events import Bar


@pytest.fixture()
def config():
    return load_config()


@pytest.fixture()
def default_raw(config):
    """A mutable copy of the raw YAML config for building variants."""
    import copy

    return copy.deepcopy(config.raw)


def make_bars(closes, market_id="TEST", start=None, freq_minutes=5):
    """Build coherent bars from a list of closes (test helper)."""
    start = start or datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        bars.append(
            Bar(
                ts=start + timedelta(minutes=freq_minutes * (i + 1)),
                market_id=market_id,
                open=float(o),
                high=float(max(o, c)),
                low=float(min(o, c)),
                close=float(c),
                volume=1000.0,
            )
        )
        prev = c
    return bars
