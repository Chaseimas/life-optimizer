"""Event-driven backtest engine.

STATUS: not implemented — Phase 5. Nothing here produces results yet.

Planned design (the contract the rest of the system is built against):

* Single chronological event loop: Bar -> strategy.on_bar -> Signal ->
  RiskManager.pre_trade_check + position sizing -> Order -> simulated
  execution (fills at the NEXT bar's open, adjusted by a SlippageModel,
  charged by the fee model, funding applied for perps) -> Fill -> portfolio
  update -> metrics.
* No component may peek forward in the bar stream; the engine owns the clock
  and hands out one completed bar at a time.
* Every simulated trade records: timestamp, market, direction, entry, exit,
  size, stop, target, fees, slippage, funding, net P&L.
* Stops/targets are evaluated against subsequent bars' high/low with
  conservative intrabar assumptions (worst-case fill ordering when both stop
  and target are touched in one bar).
* Output feeds backtesting.metrics and the report generator.
"""

from __future__ import annotations


class BacktestEngine:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "BacktestEngine is scheduled for Phase 5 (event-driven backtester). "
            "No backtests can be run yet, and no results exist."
        )
