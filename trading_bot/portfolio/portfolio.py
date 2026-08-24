"""Portfolio engine.

STATUS: not implemented — Phase 12 (cross-market comparison / portfolio mode).

Planned design:
* Compare a strategy across MNQ, BTC, ETH and other liquid markets on
  identical terms (same logic, market-specific costs), and measure where the
  edge, costs, liquidity and drawdowns are actually best — no venue is
  assumed better a priori.
* Diversification must EARN its place: a multi-market portfolio is adopted
  only if it improves Sharpe/Sortino/drawdown/return stability versus the
  best single market. Markets are never added just to trade more.
* Aggregate exposure feeds the risk manager's max_open_exposure check.
"""

from __future__ import annotations


class PortfolioEngine:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "PortfolioEngine is scheduled for Phase 12. Nothing is implemented yet."
        )
