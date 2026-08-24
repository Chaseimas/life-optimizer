"""Simulated execution for the backtester.

STATUS: not implemented — Phase 5/6.

Planned design:
* SimulatedExecutor implements the same BaseExecutor interface as the live
  venues, so strategy/risk code cannot tell the difference (this is what
  makes paper and live share one code path later).
* Market orders fill at next bar open +/- slippage; limit orders fill only
  if the bar trades through the limit price; stops trigger on touch with
  conservative assumptions.
* Partial fills and order rejection paths are modeled so the order-state
  tests mean something.
"""

from __future__ import annotations


class SimulatedExecutor:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "SimulatedExecutor is scheduled for Phase 5/6. Nothing is implemented yet."
        )
