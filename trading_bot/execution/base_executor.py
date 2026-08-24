"""Base execution interface.

The strategy/signal/risk layers talk ONLY to this interface. Venue specifics
(CME vs. Hyperliquid) live in subclasses, so the same research code can be
pointed at any market.

Order flow on every submit:
    kill-switch check  ->  order validation (tick/size/notional)  ->  _submit()

Gating:
* PAPER mode: always constructible (simulated routing arrives in Phases 5/13).
* LIVE mode: requires config ``execution.mode: live``, ``live.enabled: true``
  and the exact confirmation phrase — otherwise ``LiveTradingDisabled`` is
  raised at construction. Subclasses add venue gates on top (e.g. Hyperliquid
  compliance). Live routing itself is Phase 15 and does not exist yet.
"""

from __future__ import annotations

import itertools
from abc import ABC, abstractmethod
from typing import ClassVar

from trading_bot.core.config import LIVE_CONFIRM_PHRASE, Config
from trading_bot.core.events import Order
from trading_bot.core.market import MarketSpec
from trading_bot.core.types import ExecutionMode, OrderType, Venue
from trading_bot.monitoring.logging import get_logger
from trading_bot.risk.kill_switch import KillSwitch

log = get_logger("execution")


class ExecutorError(RuntimeError):
    pass


class LiveTradingDisabled(ExecutorError):
    pass


class ComplianceGate(ExecutorError):
    pass


class OrderValidationError(ExecutorError):
    pass


class BaseExecutor(ABC):
    venue: ClassVar[Venue]

    def __init__(
        self,
        spec: MarketSpec,
        config: Config,
        kill_switch: KillSwitch,
        mode: ExecutionMode = ExecutionMode.PAPER,
    ):
        if spec.venue is not self.venue:
            raise ExecutorError(
                f"{type(self).__name__} handles venue {self.venue.value!r}, "
                f"got market {spec.market_id!r} on {spec.venue.value!r}"
            )
        self.spec = spec
        self.config = config
        self.kill_switch = kill_switch
        self.mode = mode
        self._order_seq = itertools.count(1)

        if mode is ExecutionMode.LIVE:
            self._assert_live_allowed(config)
            self._venue_live_gate(config)

    # ---- gating --------------------------------------------------------------
    def _assert_live_allowed(self, config: Config) -> None:
        live = config.execution.live
        if config.execution.mode != "live" or not live.enabled:
            raise LiveTradingDisabled(
                "Live trading is DISABLED. It requires execution.mode: live and "
                "execution.live.enabled: true in config.yaml — and live execution "
                "itself is Phase 15 and not yet implemented."
            )
        if live.confirm_phrase != LIVE_CONFIRM_PHRASE:
            raise LiveTradingDisabled(
                "Live trading requires the exact confirmation phrase "
                f"{LIVE_CONFIRM_PHRASE!r} in execution.live.confirm_phrase."
            )

    def _venue_live_gate(self, config: Config) -> None:
        """Subclasses raise here if their venue has extra live requirements."""

    # ---- order path ----------------------------------------------------------
    def submit_order(self, order: Order) -> str:
        """Validate and route an order. Returns the order id."""
        self.kill_switch.assert_ok()
        self.validate_order(order)
        if order.order_id is None:
            order.order_id = f"{self.spec.market_id}-{next(self._order_seq)}"
        return self._submit(order)

    def validate_order(self, order: Order) -> None:
        s = self.spec
        if order.market_id != s.market_id:
            raise OrderValidationError(
                f"order market {order.market_id!r} != executor market {s.market_id!r}"
            )
        if order.qty <= 0:
            raise OrderValidationError("order qty must be > 0")
        if not s.is_valid_size(order.qty):
            raise OrderValidationError(
                f"qty {order.qty} violates size step {s.size_step} / min size {s.min_size} "
                f"for {s.market_id}"
            )
        for label, px in (("limit_price", order.limit_price), ("stop_price", order.stop_price),
                          ("stop_loss", order.stop_loss), ("take_profit", order.take_profit)):
            if px is not None and not s.is_valid_price(px):
                raise OrderValidationError(
                    f"{label}={px} is not on the {s.tick_size} tick grid for {s.market_id}"
                )
        if order.order_type is OrderType.LIMIT and order.limit_price is None:
            raise OrderValidationError("limit order requires limit_price")
        if s.min_notional:
            ref = order.limit_price or order.stop_price
            if ref is not None and s.notional(ref, order.qty) < s.min_notional:
                raise OrderValidationError(
                    f"notional below venue minimum {s.min_notional} for {s.market_id}"
                )

    # ---- venue implementation ------------------------------------------------
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def _submit(self, order: Order) -> str: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> None: ...

    @abstractmethod
    def get_positions(self) -> dict: ...

    @abstractmethod
    def get_account(self) -> dict: ...
