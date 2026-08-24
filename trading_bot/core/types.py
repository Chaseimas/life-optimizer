"""Shared enums used across strategy, risk, execution and backtesting layers."""

from __future__ import annotations

from enum import Enum, IntEnum


class Side(IntEnum):
    """Trade direction. Integer values so that ``pnl = (exit - entry) * side``."""

    LONG = 1
    FLAT = 0
    SHORT = -1


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderStatus(str, Enum):
    NEW = "new"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class ExecutionMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class Venue(str, Enum):
    CME = "cme"
    HYPERLIQUID = "hyperliquid"


class Liquidity(str, Enum):
    MAKER = "maker"
    TAKER = "taker"
