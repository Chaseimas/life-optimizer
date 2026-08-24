"""Risk manager: hard pre-trade checks and daily/overall loss controls.

Semantics:

* Daily loss limit hit         -> HALT for the rest of the trading day (latched;
                                  only ``start_new_day`` with a NEW date clears it).
* Max trades/day reached       -> no new trades today.
* Max consecutive losses       -> HALT for the rest of the day; the streak
                                  counter resets on the next trading day.
* Max drawdown from peak hit   -> trips the KILL SWITCH (human reset required).
* Exposure cap                 -> per-order denial.

The strategy layer cannot reset anything here. ``start_new_day`` must be
called by the engine's clock with an advancing date; passing the same date
again is rejected so a strategy can never "refresh" its own limits.

Position size is NEVER increased after losses. Nothing in this class scales
size at all — it only ever says yes/no; sizing lives in position_sizing.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trading_bot.core.config import RiskLimits
from trading_bot.monitoring.logging import get_logger
from trading_bot.risk.kill_switch import KillSwitch, KillSwitchReason

log = get_logger("risk_manager")


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str = "ok"

    def __bool__(self) -> bool:
        return self.allowed


class RiskManager:
    def __init__(self, limits: RiskLimits, kill_switch: KillSwitch, starting_equity: float):
        if starting_equity <= 0:
            raise ValueError("starting_equity must be > 0")
        limits.validate()
        self.limits = limits
        self.kill_switch = kill_switch
        self.equity = float(starting_equity)
        self.peak_equity = float(starting_equity)

        self.current_day: date | None = None
        self.daily_pnl = 0.0
        self.trades_today = 0
        self.consecutive_losses = 0
        self._daily_halt_reason: str | None = None

    # ---- clock ---------------------------------------------------------------
    def start_new_day(self, day: date) -> None:
        """Reset daily counters. Must be called with an ADVANCING date."""
        if self.current_day is not None and day <= self.current_day:
            raise ValueError(
                f"start_new_day({day}) rejected: current day is {self.current_day}. "
                "Daily limits cannot be reset within the same day."
            )
        self.current_day = day
        self.daily_pnl = 0.0
        self.trades_today = 0
        self.consecutive_losses = 0
        self._daily_halt_reason = None

    # ---- recording -----------------------------------------------------------
    def record_trade_opened(self) -> None:
        self.trades_today += 1

    def record_closed_trade(self, pnl: float) -> None:
        """Record a closed trade's net P&L; updates equity, streaks, halts."""
        self.daily_pnl += pnl
        self.equity += pnl
        self.peak_equity = max(self.peak_equity, self.equity)

        if pnl < 0:
            self.consecutive_losses += 1
        elif pnl > 0:
            self.consecutive_losses = 0

        if self.daily_pnl <= -self.limits.max_daily_loss and self._daily_halt_reason is None:
            self._daily_halt_reason = (
                f"daily loss limit hit ({self.daily_pnl:.2f} <= -{self.limits.max_daily_loss:.2f})"
            )
            log.warning("HALT FOR THE DAY: %s", self._daily_halt_reason)

        if self.consecutive_losses >= self.limits.max_consecutive_losses and self._daily_halt_reason is None:
            self._daily_halt_reason = (
                f"{self.consecutive_losses} consecutive losses "
                f"(limit {self.limits.max_consecutive_losses})"
            )
            log.warning("HALT FOR THE DAY: %s", self._daily_halt_reason)

        drawdown = 0.0 if self.peak_equity <= 0 else 1.0 - self.equity / self.peak_equity
        # Small tolerance so a loss of exactly the limit (e.g. 10.000%) trips
        # despite float rounding — the conservative direction.
        if drawdown >= self.limits.max_drawdown - 1e-12:
            self.kill_switch.trip(
                KillSwitchReason.MAX_DRAWDOWN,
                f"drawdown {drawdown:.2%} >= limit {self.limits.max_drawdown:.2%}",
            )

    # ---- pre-trade gate ------------------------------------------------------
    def pre_trade_check(
        self, proposed_notional: float = 0.0, current_open_exposure: float = 0.0
    ) -> RiskDecision:
        if self.kill_switch.is_tripped:
            return RiskDecision(False, "kill switch engaged")
        if self.current_day is None:
            return RiskDecision(False, "no trading day started (engine must call start_new_day)")
        if self._daily_halt_reason is not None:
            return RiskDecision(False, f"halted for the day: {self._daily_halt_reason}")
        if self.daily_pnl <= -self.limits.max_daily_loss:
            self._daily_halt_reason = "daily loss limit hit"
            return RiskDecision(False, "halted for the day: daily loss limit hit")
        if self.trades_today >= self.limits.max_trades_per_day:
            return RiskDecision(
                False, f"max trades per day reached ({self.limits.max_trades_per_day})"
            )
        if current_open_exposure + proposed_notional > self.limits.max_open_exposure:
            return RiskDecision(
                False,
                f"exposure {current_open_exposure + proposed_notional:.2f} would exceed "
                f"max_open_exposure {self.limits.max_open_exposure:.2f}",
            )
        return RiskDecision(True, "ok")
