"""Cross-market correlation analysis.

STATUS: not implemented — Phase 12.

Planned design:
* Rolling return correlations between candidate markets (MNQ vs BTC vs ETH),
  plus correlation of the STRATEGY's daily P&L streams across markets — the
  latter is what actually matters for diversification.
* Correlation regimes shift (crypto/equity correlation is famously unstable);
  report rolling windows and stress periods, not one full-sample number.
"""

from __future__ import annotations


def strategy_pnl_correlation(*args, **kwargs):
    raise NotImplementedError(
        "Correlation analysis is scheduled for Phase 12. Nothing is implemented yet."
    )
