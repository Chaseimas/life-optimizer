"""Slippage models.

Convention: ``direction`` is the ORDER direction (+1 buy, -1 sell). Slippage
always moves the fill AGAINST the trader: buys fill higher, sells fill lower.
A slippage model returning the reference price unchanged (perfect fills) is
deliberately not provided.

Phase 5 will add depth/volume-aware models; these two are the honest minimum
for early research.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from trading_bot.core.market import MarketSpec


class SlippageModel(ABC):
    @abstractmethod
    def fill_price(self, spec: MarketSpec, direction: int, ref_price: float, size: float) -> float:
        """Adjusted fill price for an order of ``size`` at ``ref_price``."""


class FixedTicksSlippage(SlippageModel):
    """Pay a fixed number of ticks per fill (default 1). Suitable default for
    liquid futures like MNQ in calm conditions — revisit with real data."""

    def __init__(self, ticks: float = 1.0):
        if ticks < 0:
            raise ValueError("ticks must be >= 0")
        self.ticks = ticks

    def fill_price(self, spec: MarketSpec, direction: int, ref_price: float, size: float) -> float:
        if direction not in (1, -1):
            raise ValueError("direction must be +1 (buy) or -1 (sell)")
        return spec.round_price(ref_price + direction * self.ticks * spec.tick_size)


class BpsSlippage(SlippageModel):
    """Pay a fixed fraction of price, quoted in basis points. Suitable default
    for crypto perps where spread scales with price."""

    def __init__(self, bps: float = 1.0):
        if bps < 0:
            raise ValueError("bps must be >= 0")
        self.bps = bps

    def fill_price(self, spec: MarketSpec, direction: int, ref_price: float, size: float) -> float:
        if direction not in (1, -1):
            raise ValueError("direction must be +1 (buy) or -1 (sell)")
        return spec.round_price(ref_price * (1.0 + direction * self.bps / 10_000.0))
