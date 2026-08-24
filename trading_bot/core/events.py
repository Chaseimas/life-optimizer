"""Event dataclasses that flow between layers.

Timestamp policy (look-ahead safety, non-negotiable):

* Every timestamp in the system MUST be timezone-aware. Naive datetimes are
  rejected at construction time so ambiguous timestamps can never enter the
  pipeline.
* A ``Bar`` represents a COMPLETED bar: ``ts`` is the bar's close time, and
  all OHLCV values were fully known at ``ts``.
* A ``Signal`` produced from a bar with close time ``t`` may only be acted on
  at ``t`` or later — in practice at the next bar's open. The backtester
  (Phase 5) enforces this convention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from trading_bot.core.types import OrderStatus, OrderType, Side


def _require_aware(ts: datetime, what: str) -> None:
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        raise ValueError(
            f"{what} timestamp must be timezone-aware (got naive {ts!r}). "
            "Naive timestamps are banned to prevent session/timezone bugs."
        )


@dataclass(frozen=True)
class Bar:
    """One completed OHLCV bar. ``ts`` is the bar CLOSE time (tz-aware)."""

    ts: datetime
    market_id: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        _require_aware(self.ts, "Bar")

    def is_coherent(self) -> bool:
        """Basic OHLC sanity (data cleaning proper is Phase 3)."""
        return (
            self.high >= self.low
            and self.high >= max(self.open, self.close)
            and self.low <= min(self.open, self.close)
            and self.volume >= 0
        )


@dataclass(frozen=True)
class Signal:
    """Strategy output. Direction only — sizing belongs to the risk engine."""

    ts: datetime
    market_id: str
    direction: Side
    strength: float = 0.0
    stop_distance: float | None = None  # in price points, if the strategy suggests one
    reason: str = ""

    def __post_init__(self) -> None:
        _require_aware(self.ts, "Signal")


@dataclass
class Order:
    ts: datetime
    market_id: str
    side: Side
    qty: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    stop_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    order_id: str | None = None
    status: OrderStatus = OrderStatus.NEW
    tags: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_aware(self.ts, "Order")


@dataclass(frozen=True)
class Fill:
    ts: datetime
    order_id: str
    market_id: str
    side: Side
    qty: float
    price: float
    fee: float
    slippage: float = 0.0

    def __post_init__(self) -> None:
        _require_aware(self.ts, "Fill")
