"""Entry point: rolling walk-forward analysis. NOT YET AVAILABLE."""

from __future__ import annotations

import sys

MESSAGE = """\
walkforward.py: walk-forward testing is Phase 9 and is not implemented yet.

It depends on the backtester (Phase 5-6) and baseline strategies (Phase 7).
The split machinery it will use already exists and is tested:
trading_bot/models/validation.py::time_series_splits (ordered, embargoed,
never shuffled).

Run the pipeline smoke test instead:  python -m trading_bot.research
"""


def main() -> int:
    print(MESSAGE)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
