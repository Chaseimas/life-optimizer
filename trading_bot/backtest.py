"""Entry point: run a backtest. NOT YET AVAILABLE."""

from __future__ import annotations

import sys

MESSAGE = """\
backtest.py: the event-driven backtester is Phase 5 and is not implemented yet.

Current status: Phase 1 (scaffolding, config, logging, experiment tracking,
abstractions, tests) is complete. Next up: Phase 2 (historical data
ingestion) and Phase 3 (cleaning) — a backtest without clean data would only
produce numbers to be fooled by.

Run the pipeline smoke test instead:  python -m trading_bot.research
"""


def main() -> int:
    print(MESSAGE)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
