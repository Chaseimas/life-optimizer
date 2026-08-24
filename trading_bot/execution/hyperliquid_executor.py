"""Hyperliquid perpetuals executor.

COMPLIANCE — read before touching this file:
* Hyperliquid is assumed NOT to be available to U.S. users. This executor is
  built so the architecture is exchange-agnostic, and stays DISABLED.
* Live use requires ALL of: the global live-trading gates (BaseExecutor),
  ``venues.hyperliquid.enabled: true``, and
  ``venues.hyperliquid.us_compliant_access: true`` — the latter may only be
  set if a lawful, compliant access path actually exists.
* This system will never bypass geographic restrictions (no VPNs, no
  intermediaries). If there is no compliant path, this stays off.

STATUS: interface + validation only. Paper simulation (Phase 13) will model
perp mechanics: hourly funding, bps fees, min notional, liquidation risk,
24/7 sessions. Live routing is Phase 15.
"""

from __future__ import annotations

from trading_bot.core.config import Config
from trading_bot.core.events import Order
from trading_bot.core.types import Venue
from trading_bot.execution.base_executor import BaseExecutor, ComplianceGate, LiveTradingDisabled

_NOT_ROUTED = (
    "Hyperliquid order routing is not implemented yet: simulated fills arrive "
    "in Phase 5/13; live connectivity is Phase 15 and additionally requires a "
    "lawful, compliant access path."
)


class HyperliquidExecutor(BaseExecutor):
    venue = Venue.HYPERLIQUID

    def _venue_live_gate(self, config: Config) -> None:
        venue_cfg = config.venues.get("hyperliquid", {})
        if not venue_cfg.get("enabled", False):
            raise LiveTradingDisabled("venues.hyperliquid.enabled is false in config.")
        if not venue_cfg.get("us_compliant_access", False):
            raise ComplianceGate(
                "Hyperliquid live trading is blocked: no compliant U.S. access "
                "path is configured (venues.hyperliquid.us_compliant_access is "
                "false). This gate must NOT be bypassed with VPNs or any other "
                "circumvention — set it true only if a lawful route exists."
            )
        raise NotImplementedError(
            "Live Hyperliquid execution is Phase 15 and intentionally not implemented."
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
