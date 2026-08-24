"""Monte Carlo analysis of backtest results.

STATUS: not implemented — Phase 10 (only runs on strategies that survive
Phases 7-9; a strategy with no out-of-sample edge never reaches this stage).

Planned design:
* Resample/shuffle the sequence of realized trades (and block-bootstrap
  daily P&L) to estimate: expected drawdown, worst-case drawdown,
  P(drawdown > X), losing-streak distribution, probability of ruin at a
  given risk fraction, and the return distribution.
* Outputs are distributions and percentiles, never a single equity curve —
  one historical path is a sample of size one, not proof.
"""

from __future__ import annotations


def monte_carlo_report(*args, **kwargs):
    raise NotImplementedError(
        "Monte Carlo analysis is scheduled for Phase 10. Nothing is implemented yet."
    )
