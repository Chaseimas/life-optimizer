"""Simulated fill logic for the event-driven backtester (Phases 5-6).

Conventions (conservative by construction):

* Market orders fill at the NEXT bar's open, adjusted by the slippage model.
  Nothing ever fills at the price that generated the signal.
* Protective stops/targets are evaluated against each bar's high/low:
  - If the bar OPENS beyond the level (gap), the fill is at the open — the
    worse price — never at the level itself.
  - If both stop and target are touched within one bar, the STOP is assumed
    to have hit first. Intrabar path is unknowable from OHLC; we take the
    loss, not the win.
* Every fill pays fees and slippage.
"""

from __future__ import annotations

from trading_bot.backtesting.slippage import SlippageModel
from trading_bot.core.events import Bar
from trading_bot.core.market import MarketSpec
from trading_bot.core.types import Side

STOP_LOSS = "stop_loss"
TAKE_PROFIT = "take_profit"


def market_fill(
    spec: MarketSpec,
    order_direction: int,          # +1 buy, -1 sell
    ref_price: float,
    size: float,
    slippage: SlippageModel,
) -> tuple[float, float]:
    """(fill_price, slippage_cost). Slippage is always adverse; cost >= 0."""
    fill = slippage.fill_price(spec, order_direction, ref_price, size)
    cost = (fill - ref_price) * order_direction * spec.point_value * size
    return fill, max(cost, 0.0)


def check_protective_exit(
    bar: Bar,
    direction: Side,
    stop_price: float | None,
    tp_price: float | None,
) -> tuple[float, str] | None:
    """Did this bar hit the stop or target? Returns (reference exit price,
    reason) or None. Stop takes precedence; gaps fill at the open."""
    d = int(direction)
    if d == 0:
        return None

    if stop_price is not None:
        gapped = (bar.open - stop_price) * d <= 0      # opened at or through the stop
        touched = (bar.low if d > 0 else bar.high) * d <= stop_price * d
        if gapped:
            return bar.open, STOP_LOSS
        if touched:
            return stop_price, STOP_LOSS

    if tp_price is not None:
        gapped = (bar.open - tp_price) * d >= 0
        touched = (bar.high if d > 0 else bar.low) * d >= tp_price * d
        if gapped:
            return bar.open, TAKE_PROFIT
        if touched:
            return tp_price, TAKE_PROFIT

    return None
