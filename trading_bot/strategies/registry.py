"""Strategy registry: name -> class, for CLIs and experiment runners."""

from __future__ import annotations

from trading_bot.strategies.base_strategy import BaseStrategy
from trading_bot.strategies.momentum import SimpleMomentum

STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    SimpleMomentum.name: SimpleMomentum,
    # Phase 7 additions (mean_reversion, vwap, breakout, regime) register here
    # once they are implemented and tested.
}


def make_strategy(name: str, params: dict | None = None) -> BaseStrategy:
    try:
        cls = STRATEGY_REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"Unknown strategy {name!r}. Implemented: {sorted(STRATEGY_REGISTRY)}"
        ) from None
    return cls(params)
