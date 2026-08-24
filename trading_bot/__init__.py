"""Algorithmic trading research and execution system.

Research-first by design:

* No live trading exists in this codebase yet (live execution is Phase 15 and
  is hard-gated behind explicit configuration).
* The goal is to discover a real, statistically defensible edge — not to
  manufacture a profitable-looking backtest.
* ~$400/day is a long-term *target* used for capital-requirement math only.
  Nothing in this system is allowed to force trades to hit a dollar number.

See trading_bot/README.md for the architecture and the phase roadmap.
"""

__version__ = "0.1.0"
