"""Entry point: paper trading. NOT YET AVAILABLE."""

from __future__ import annotations

import sys

MESSAGE = """\
paper_trade.py: paper trading is Phase 13 and is not implemented yet.

Paper trading only makes sense once a strategy has survived backtesting
(Phases 5-7), out-of-sample and walk-forward validation (8-9) and Monte
Carlo analysis (10). Running it earlier would just paper-trade noise.

Run the pipeline smoke test instead:  python -m trading_bot.research
"""


def main() -> int:
    print(MESSAGE)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
