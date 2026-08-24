"""Paper trader.

STATUS: not implemented — Phase 13, after the backtester (5-6) and a strategy
that survived out-of-sample, walk-forward and Monte Carlo testing (7-10).

Planned design:
* Runs the SAME signal logic, risk engine, position sizing, execution
  interface and stop logic as the eventual live system — the only difference
  is the executor is simulated. No separate strategy implementation, ever.
* Logs per trade: signal, intended entry, simulated actual entry, stop,
  target, size, exit, P&L, fees, slippage, reason for entry, reason for exit.
* Runs against live market data in real time so latency/staleness issues
  surface before money is involved.
"""

from __future__ import annotations


class PaperTrader:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "PaperTrader is scheduled for Phase 13, after a strategy has "
            "survived Phases 7-10. Nothing is implemented yet."
        )
