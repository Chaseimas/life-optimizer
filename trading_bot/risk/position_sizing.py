"""Position sizing: risk first, always.

Size is derived from (equity, stop distance, risk-per-trade, volatility via the
stop, exposure caps). There is deliberately NO input for a profit target:
"how much do we need to make today" is not a sizing variable and never will be.

Sizing always rounds DOWN and applies every cap. If any input is degenerate
(no stop, non-positive equity), the size is zero — no trade.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from trading_bot.core.config import RiskLimits
from trading_bot.core.market import MarketSpec


@dataclass(frozen=True)
class SizingResult:
    size: float                       # units (contracts / coins); 0 = do not trade
    risk_amount: float                # currency at risk between entry and stop
    notional: float                   # currency exposure at entry
    capped_by: tuple = ()             # which caps reduced the raw size
    reason: str = "ok"                # why size is 0, when it is


def compute_position_size(
    *,
    equity: float,
    price: float,
    stop_distance: float,
    spec: MarketSpec,
    limits: RiskLimits,
    risk_per_trade: float | None = None,
    current_open_exposure: float = 0.0,
) -> SizingResult:
    """Risk-based fixed-fractional sizing with hard caps.

    size_raw = (equity * risk_per_trade) / (stop_distance * point_value)
    then capped by: venue size step (floor), max_position_size,
    max_open_exposure (minus what is already open), venue minimums.
    """
    rpt = limits.max_risk_per_trade if risk_per_trade is None else min(
        risk_per_trade, limits.max_risk_per_trade
    )

    if equity <= 0:
        return SizingResult(0.0, 0.0, 0.0, (), "equity <= 0")
    if price <= 0:
        return SizingResult(0.0, 0.0, 0.0, (), "price <= 0")
    if stop_distance is None or stop_distance <= 0:
        return SizingResult(0.0, 0.0, 0.0, (), "no valid stop distance — refusing to size without a stop")

    risk_amount = equity * rpt
    raw = risk_amount / (stop_distance * spec.point_value)

    capped: list[str] = []
    size = spec.round_size(raw)
    if size < raw - spec.size_step * 1e-6:
        capped.append("size_step")

    if size > limits.max_position_size:
        size = spec.round_size(limits.max_position_size)
        capped.append("max_position_size")

    exposure_budget = limits.max_open_exposure - max(current_open_exposure, 0.0)
    if exposure_budget <= 0:
        return SizingResult(0.0, risk_amount, 0.0, ("max_open_exposure",), "exposure budget exhausted")
    unit_notional = spec.notional(price, 1.0)
    if spec.notional(price, size) > exposure_budget:
        size = spec.round_size(exposure_budget / unit_notional)
        capped.append("max_open_exposure")

    if size < spec.min_size:
        return SizingResult(
            0.0, risk_amount, 0.0, tuple(capped), "resulting size below venue minimum — no trade"
        )
    notional = spec.notional(price, size)
    if spec.min_notional and notional < spec.min_notional:
        return SizingResult(
            0.0, risk_amount, 0.0, tuple(capped), "notional below venue minimum — no trade"
        )

    return SizingResult(size, risk_amount, notional, tuple(capped), "ok")
