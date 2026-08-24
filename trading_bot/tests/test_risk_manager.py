"""Risk manager: daily loss halt, trade caps, streaks, drawdown kill switch,
and the impossibility of a strategy resetting its own limits."""

from __future__ import annotations

from datetime import date

import pytest

from trading_bot.core.config import RiskLimits
from trading_bot.risk.kill_switch import RESET_CONFIRM_PHRASE, KillSwitch
from trading_bot.risk.risk_manager import RiskManager

LIMITS = RiskLimits(
    max_daily_loss=300.0,
    max_risk_per_trade=0.005,
    max_position_size=3,
    max_trades_per_day=3,
    max_drawdown=0.10,
    max_open_exposure=60_000.0,
    max_consecutive_losses=3,
)


def fresh(equity=10_000.0):
    rm = RiskManager(LIMITS, KillSwitch(), starting_equity=equity)
    rm.start_new_day(date(2026, 1, 5))
    return rm


def test_no_trading_before_day_started():
    rm = RiskManager(LIMITS, KillSwitch(), starting_equity=10_000)
    decision = rm.pre_trade_check()
    assert not decision
    assert "start_new_day" in decision.reason


def test_allows_trade_under_limits():
    rm = fresh()
    assert rm.pre_trade_check(proposed_notional=40_000)


def test_daily_loss_limit_halts_for_the_day():
    rm = fresh()
    rm.record_closed_trade(-300.0)
    decision = rm.pre_trade_check()
    assert not decision
    assert "daily loss" in decision.reason
    # Next day trading resumes (kill switch NOT tripped by a daily halt).
    rm.start_new_day(date(2026, 1, 6))
    assert rm.pre_trade_check()


def test_daily_limits_cannot_be_reset_same_day():
    rm = fresh()
    rm.record_closed_trade(-300.0)
    with pytest.raises(ValueError, match="cannot be reset"):
        rm.start_new_day(date(2026, 1, 5))  # same day
    with pytest.raises(ValueError):
        rm.start_new_day(date(2026, 1, 4))  # going backwards is worse


def test_max_trades_per_day():
    rm = fresh()
    for _ in range(3):
        rm.record_trade_opened()
    decision = rm.pre_trade_check()
    assert not decision
    assert "max trades" in decision.reason


def test_consecutive_losses_halt():
    rm = fresh()
    for _ in range(3):
        rm.record_closed_trade(-10.0)  # small: daily loss limit NOT hit
    decision = rm.pre_trade_check()
    assert not decision
    assert "consecutive losses" in decision.reason
    rm.start_new_day(date(2026, 1, 6))
    assert rm.pre_trade_check()


def test_win_resets_loss_streak():
    rm = fresh()
    rm.record_closed_trade(-10.0)
    rm.record_closed_trade(-10.0)
    rm.record_closed_trade(5.0)
    assert rm.consecutive_losses == 0
    assert rm.pre_trade_check()


def test_max_drawdown_trips_kill_switch():
    rm = fresh(equity=10_000)
    rm.record_closed_trade(-1_000.0)  # exactly 10% off peak
    assert rm.kill_switch.is_tripped
    assert not rm.pre_trade_check()
    # A new day does NOT clear a kill-switch trip...
    rm.start_new_day(date(2026, 1, 6))
    decision = rm.pre_trade_check()
    assert not decision
    assert "kill switch" in decision.reason
    # ...only an explicit human reset does.
    rm.kill_switch.reset(RESET_CONFIRM_PHRASE)
    assert rm.pre_trade_check()


def test_exposure_denied_per_order():
    rm = fresh()
    decision = rm.pre_trade_check(proposed_notional=40_000, current_open_exposure=40_000)
    assert not decision
    assert "exposure" in decision.reason


def test_equity_tracking():
    rm = fresh(equity=10_000)
    rm.record_closed_trade(200.0)
    rm.record_closed_trade(-50.0)
    assert rm.equity == pytest.approx(10_150.0)
    assert rm.peak_equity == pytest.approx(10_200.0)
