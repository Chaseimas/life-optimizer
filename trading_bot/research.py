"""Entry point: run the Phase 1 research pipeline smoke experiment.

Thin wrapper so ``python trading_bot/research.py`` works from the repo root;
the actual runner lives in ``trading_bot/research/__main__.py`` (also
reachable as ``python -m trading_bot.research``).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading_bot.research.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
