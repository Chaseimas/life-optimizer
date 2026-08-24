"""Kill switch: trips latch, resets are human-only, manual file works."""

from __future__ import annotations

import pytest

from trading_bot.risk.kill_switch import (
    RESET_CONFIRM_PHRASE,
    KillSwitch,
    KillSwitchReason,
    KillSwitchTripped,
)


def test_starts_disengaged():
    ks = KillSwitch()
    assert not ks.is_tripped
    ks.assert_ok()  # must not raise


def test_trip_latches_and_blocks():
    ks = KillSwitch()
    ks.trip(KillSwitchReason.DATA_FEED_FAILURE, "feed gap > 30s")
    assert ks.is_tripped
    with pytest.raises(KillSwitchTripped, match="data_feed_failure"):
        ks.assert_ok()
    assert len(ks.history) == 1
    assert ks.history[0].reason is KillSwitchReason.DATA_FEED_FAILURE


def test_reset_requires_exact_phrase():
    ks = KillSwitch()
    ks.trip(KillSwitchReason.EXECUTION_ERROR)
    with pytest.raises(PermissionError):
        ks.reset("please")
    assert ks.is_tripped
    ks.reset(RESET_CONFIRM_PHRASE)
    assert not ks.is_tripped
    # History survives reset — trips are never erased.
    assert len(ks.history) == 1


def test_manual_sentinel_file_trips(tmp_path):
    sentinel = tmp_path / "KILL_SWITCH"
    ks = KillSwitch(manual_file=sentinel)
    assert not ks.is_tripped
    sentinel.touch()
    assert ks.is_tripped
    with pytest.raises(KillSwitchTripped):
        ks.assert_ok()


def test_reset_refused_while_sentinel_exists(tmp_path):
    sentinel = tmp_path / "KILL_SWITCH"
    sentinel.touch()
    ks = KillSwitch(manual_file=sentinel)
    assert ks.is_tripped
    with pytest.raises(PermissionError, match="sentinel"):
        ks.reset(RESET_CONFIRM_PHRASE)
    sentinel.unlink()
    ks.reset(RESET_CONFIRM_PHRASE)
    assert not ks.is_tripped
