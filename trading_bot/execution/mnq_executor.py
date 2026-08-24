"""MNQ (CME micro futures) executor.

STATUS: interface + validation only. Order routing is not implemented:
* Simulated fills arrive with the backtest engine (Phase 5) and paper trader
  (Phase 13).
* Real brokerage connectivity (e.g. via a futures broker API) is Phase 15 and
  requires the live-trading gates in BaseExecutor.

What IS enforced today: whole-contract sizes, prices on the 0.25 tick grid,
venue enablement, and the kill-switch check on every submit.
"""

from __future__ import annotations

from trading_bot.core.config import Config
from trading_bot.core.events import Order
from trading_bot.core.types import Venue
from trading_bot.execution.base_executor import BaseExecutor, LiveTradingDisabled

_NOT_ROUTED = (
    "MNQ order routing is not implemented yet: simulated fills arrive in "
    "Phase 5 (backtester) / Phase 13 (paper trading); live brokerage "
    "connectivity is Phase 15."
)


class MNQExecutor(BaseExecutor):
    venue = Venue.CME

    def _venue_live_gate(self, config: Config) -> None:
        venue_cfg = config.venues.get("cme", {})
        if not venue_cfg.get("enabled", False):
            raise LiveTradingDisabled("venues.cme.enabled is false in config.")
        raise NotImplementedError(
            "Live CME execution is Phase 15 and intentionally not implemented. "
            "Complete research, out-of-sample validation and paper trading first."
        )

    def connect(self) -> None:
        raise NotImplementedError(_NOT_ROUTED)

    def _submit(self, order: Order) -> str:
        raise NotImplementedError(_NOT_ROUTED)

    def cancel_order(self, order_id: str) -> None:
        raise NotImplementedError(_NOT_ROUTED)

    def get_positions(self) -> dict:
        raise NotImplementedError(_NOT_ROUTED)

    def get_account(self) -> dict:
        raise NotImplementedError(_NOT_ROUTED)
