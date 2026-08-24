"""Continuous futures construction: roll detection and back-adjustment."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.data_pipeline.continuous import build_continuous, detect_roll_ts
from trading_bot.data_pipeline.frames import DataError


def contract(start: str, days: int, price0: float, vol_profile, tz="UTC"):
    """Daily bars with a volume profile (list of daily volumes)."""
    idx = pd.date_range(start, periods=days, freq="1D", tz=tz)
    closes = price0 + np.arange(days) * 1.0
    return pd.DataFrame(
        {
            "open": closes - 0.5,
            "high": closes + 1.0,
            "low": closes - 1.0,
            "close": closes,
            "volume": vol_profile,
        },
        index=idx,
    )


def test_volume_crossover_detection():
    # Front fades, back grows: crossover on day 6 (index 5), confirmed on day 7.
    front = contract("2024-03-01", 10, 100.0, [1000, 900, 800, 700, 600, 400, 300, 200, 100, 50])
    back = contract("2024-03-01", 10, 110.0, [10, 20, 50, 100, 300, 500, 600, 700, 900, 1200])
    rts = detect_roll_ts(front, back, confirm_days=2)
    # back > front on days 6 and 7 (2024-03-06, 03-07) -> roll from 03-08
    assert rts == pd.Timestamp("2024-03-08", tz="UTC")


def test_stitch_is_jump_free_and_back_adjusted():
    front = contract("2024-03-01", 10, 100.0, [1000] * 5 + [100] * 5)
    back = contract("2024-03-01", 10, 105.0, [10] * 5 + [2000] * 5)  # constant +5 basis
    cont, events = build_continuous([("MNQH4", front), ("MNQM4", back)], confirm_days=2)

    assert len(events) == 1
    ev = events[0]
    assert ev.from_contract == "MNQH4" and ev.to_contract == "MNQM4"
    assert ev.price_offset == pytest.approx(5.0)

    # After the roll the series equals the new contract; before it, the old
    # contract shifted up by the offset -> continuous returns have no jump.
    pre = cont.loc[: ev.ts - pd.Timedelta(days=1), "close"]
    expected_pre = front.loc[pre.index, "close"] + 5.0
    assert np.allclose(pre.values, expected_pre.values)
    post = cont.loc[ev.ts:, "close"]
    assert np.allclose(post.values, back.loc[post.index, "close"].values)

    # The spliced boundary must show the normal +1/day drift, not a basis jump.
    boundary_ret = cont["close"].diff().loc[ev.ts]
    assert boundary_ret == pytest.approx(1.0)


def test_three_contracts_cumulative_offsets():
    c1 = contract("2024-03-01", 8, 100.0, [1000] * 4 + [10] * 4)
    c2 = contract("2024-03-01", 16, 103.0, [5] * 4 + [1000] * 6 + [10] * 6)
    c3 = contract("2024-03-05", 12, 107.0, [5] * 6 + [1000] * 6)
    cont, events = build_continuous([("A", c1), ("B", c2), ("C", c3)], confirm_days=2)
    assert len(events) == 2
    # Earliest segment carries BOTH offsets; no duplicate timestamps.
    assert not cont.index.has_duplicates
    assert cont.index.is_monotonic_increasing
    # Jump-free at both boundaries:
    for ev in events:
        assert cont["close"].diff().loc[ev.ts] == pytest.approx(1.0)


def test_explicit_roll_ts_overrides_detection():
    front = contract("2024-03-01", 10, 100.0, [1000] * 10)   # volume never crosses
    back = contract("2024-03-01", 10, 105.0, [10] * 10)
    rts = pd.Timestamp("2024-03-06", tz="UTC")
    cont, events = build_continuous(
        [("F", front), ("B", back)], roll_ts={"F": rts}
    )
    assert events[0].ts == rts
    assert cont.loc[rts, "close"] == back.loc[rts, "close"]


def test_no_overlap_and_no_roll_ts_raises():
    a = contract("2024-01-01", 5, 100.0, [100] * 5)
    b = contract("2024-06-01", 5, 105.0, [100] * 5)
    with pytest.raises(DataError, match="roll"):
        build_continuous([("A", a), ("B", b)])
