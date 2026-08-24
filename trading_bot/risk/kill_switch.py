"""Kill switch: a latch that halts all trading.

Rules:
* Anything can TRIP it (data feed failure, stale prices, API disconnect,
  execution errors, abnormal slippage, inconsistent account/position state,
  max drawdown, unexpected order behavior, or a human).
* Only a human can RESET it, with an explicit confirmation phrase.
* A manual sentinel file (``trading_bot/KILL_SWITCH`` by default) also trips
  it: ``touch trading_bot/KILL_SWITCH`` is the emergency stop that works even
  if the process is misbehaving. While the file exists, reset is refused.
* The strategy layer has no API to reset it. By design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from trading_bot.monitoring.logging import get_logger

RESET_CONFIRM_PHRASE = "RESET-KILL-SWITCH"

log = get_logger("kill_switch")


class KillSwitchReason(str, Enum):
    DATA_FEED_FAILURE = "data_feed_failure"
    STALE_PRICES = "stale_prices"
    API_DISCONNECT = "api_disconnect"
    EXECUTION_ERROR = "execution_error"
    ABNORMAL_SLIPPAGE = "abnormal_slippage"
    ACCOUNT_INCONSISTENT = "account_inconsistent"
    POSITION_INCONSISTENT = "position_inconsistent"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    MAX_DRAWDOWN = "max_drawdown"
    UNEXPECTED_ORDER_BEHAVIOR = "unexpected_order_behavior"
    MANUAL = "manual"


class KillSwitchTripped(RuntimeError):
    """Raised when an action is attempted while the kill switch is engaged."""


@dataclass(frozen=True)
class TripEvent:
    ts: datetime
    reason: KillSwitchReason
    detail: str = ""


@dataclass
class KillSwitch:
    manual_file: Path | None = None
    _tripped: bool = False
    _history: list[TripEvent] = field(default_factory=list)

    # ---- state -------------------------------------------------------------
    @property
    def is_tripped(self) -> bool:
        if self.manual_file is not None and self.manual_file.exists():
            if not self._tripped:
                self.trip(
                    KillSwitchReason.MANUAL,
                    f"manual sentinel file present: {self.manual_file}",
                )
            return True
        return self._tripped

    @property
    def history(self) -> tuple[TripEvent, ...]:
        return tuple(self._history)

    # ---- actions -----------------------------------------------------------
    def trip(self, reason: KillSwitchReason, detail: str = "") -> None:
        event = TripEvent(datetime.now(timezone.utc), reason, detail)
        self._history.append(event)
        if not self._tripped:
            self._tripped = True
            log.critical("KILL SWITCH TRIPPED: %s %s", reason.value, detail)

    def assert_ok(self) -> None:
        """Raise ``KillSwitchTripped`` if trading must halt. Call before every
        order-affecting action."""
        if self.is_tripped:
            last = self._history[-1] if self._history else None
            raise KillSwitchTripped(
                f"Kill switch engaged"
                + (f" (last reason: {last.reason.value} {last.detail})" if last else "")
                + ". Trading halted."
            )

    def reset(self, confirm_phrase: str) -> None:
        """Human-only reset. Refused while the manual sentinel file exists."""
        if confirm_phrase != RESET_CONFIRM_PHRASE:
            raise PermissionError(
                f"Kill switch reset requires confirm_phrase={RESET_CONFIRM_PHRASE!r}."
            )
        if self.manual_file is not None and self.manual_file.exists():
            raise PermissionError(
                f"Manual sentinel file still present: {self.manual_file}. "
                "Delete it first if you really intend to resume."
            )
        self._tripped = False
        log.warning("Kill switch reset by operator.")
