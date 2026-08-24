"""Live trader.

STATUS: intentionally not implemented — Phase 15, the LAST phase.

Preconditions before this file gains any live capability:
1. Backtester validated (Phases 5-6), baseline strategies evaluated (7),
   out-of-sample + walk-forward + Monte Carlo passed (8-10), and a
   statistically defensible edge demonstrated — or the honest conclusion
   that none exists, in which case this file never gets written.
2. Paper trading (13) run with the same code path, with acceptable tracking
   between simulated and observed fills.
3. Explicit configuration: execution.mode: live, live.enabled: true and the
   confirmation phrase (see core/config.py). Never enabled by default.
4. Smallest practical position size at the start.

The live trader will reuse the paper trader's entire loop with only the
executor swapped — shared code path is the whole point.
"""

from __future__ import annotations


class LiveTrader:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "LIVE TRADING IS NOT IMPLEMENTED (Phase 15). It requires a proven "
            "out-of-sample edge, completed paper trading, and explicit "
            "configuration. There is no way to trade real money with this "
            "codebase today — by design."
        )
