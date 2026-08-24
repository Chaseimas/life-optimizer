"""Entry point: live trading. REFUSES TO RUN — by design."""

from __future__ import annotations

import sys

MESSAGE = """\
==============================================================================
 LIVE TRADING IS NOT AVAILABLE.
==============================================================================
live_trade.py is Phase 15, the FINAL phase, and is intentionally not
implemented. Before this script will ever do anything, ALL of the following
must be true:

  1. A statistically defensible edge demonstrated on out-of-sample data
     (Phases 5-10) — not an optimized historical curve.
  2. Paper trading (Phase 13) completed with the same code path, with
     acceptable slippage/fill tracking versus simulation.
  3. Explicit configuration in config.yaml:
         execution.mode: live
         execution.live.enabled: true
         execution.live.confirm_phrase: <exact phrase, see core/config.py>
  4. Smallest practical position size to start.

If no edge is found during research, this phase never happens at all.
==============================================================================
"""


def main() -> int:
    print(MESSAGE)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
