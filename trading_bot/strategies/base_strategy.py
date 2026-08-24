"""Strategy abstraction.

LOOK-AHEAD CONTRACT (the most important rule in this file):

* ``on_bar(bar)`` is called once per COMPLETED bar, in strict chronological
  order. At that moment the strategy may use ONLY: this bar and bars it has
  already seen. Nothing else exists yet.
* A signal returned for bar ``t`` may be acted on no earlier than the next
  bar. The backtester (Phase 5) enforces next-bar execution.
* Strategies must be deterministic given the same bar sequence: same input,
  same signals. ``tests/test_lookahead.py`` verifies that truncating the
  future does not change past signals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from trading_bot.core.events import Bar, Signal


class BaseStrategy(ABC):
    name: ClassVar[str] = "base"

    def __init__(self, params: dict | None = None):
        self.params = {**self.default_params(), **(params or {})}
        unknown = set(self.params) - set(self.default_params())
        if unknown:
            raise ValueError(f"{self.name}: unknown params {sorted(unknown)}")

    @classmethod
    def default_params(cls) -> dict:
        return {}

    @property
    @abstractmethod
    def warmup_bars(self) -> int:
        """Bars needed before the first signal can be produced."""

    @abstractmethod
    def on_bar(self, bar: Bar) -> Signal | None:
        """Consume one completed bar; optionally emit a signal."""

    def reset(self) -> None:
        """Clear internal state so the instance can replay another series."""

    def describe(self) -> dict:
        return {"name": self.name, "params": dict(self.params), "warmup_bars": self.warmup_bars}
