"""Fee models.

Two modes, driven by the MarketSpec:
* PER_CONTRACT (futures): flat currency per contract per side.
* BPS_NOTIONAL (perps): fraction of traded notional, maker/taker aware.

Fees are always >= 0 and are charged on every side of every trade. The
backtester must never assume free execution.
"""

from __future__ import annotations

from trading_bot.core.market import FeeMode, MarketSpec
from trading_bot.core.types import Liquidity


def fee_for_fill(
    spec: MarketSpec,
    price: float,
    size: float,
    liquidity: Liquidity = Liquidity.TAKER,
) -> float:
    """Fee (account currency) for one fill of ``size`` units at ``price``."""
    if size <= 0:
        return 0.0
    rate = spec.fees.rate(liquidity)
    if spec.fees.mode is FeeMode.PER_CONTRACT:
        return rate * size
    return spec.notional(price, size) * rate


def round_trip_fee(
    spec: MarketSpec,
    entry_price: float,
    exit_price: float,
    size: float,
    liquidity: Liquidity = Liquidity.TAKER,
) -> float:
    """Total fees for entering and exiting a position."""
    return fee_for_fill(spec, entry_price, size, liquidity) + fee_for_fill(
        spec, exit_price, size, liquidity
    )
