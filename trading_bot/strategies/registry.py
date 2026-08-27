"""Strategy registry: name -> class, for CLIs and experiment runners."""

from __future__ import annotations

from trading_bot.strategies.base_strategy import BaseStrategy
from trading_bot.strategies.breakout import OpeningRangeBreakout
from trading_bot.strategies.mean_reversion import ZScoreMeanReversion
from trading_bot.strategies.momentum import SimpleMomentum
from trading_bot.strategies.regime import RegimeGatedMomentum
from trading_bot.strategies.vol_breakout import VolatilityBreakout
from trading_bot.strategies.vwap import RollingVWAPStrategy

STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    SimpleMomentum.name: SimpleMomentum,
    ZScoreMeanReversion.name: ZScoreMeanReversion,
    RollingVWAPStrategy.name: RollingVWAPStrategy,
    OpeningRangeBreakout.name: OpeningRangeBreakout,
    RegimeGatedMomentum.name: RegimeGatedMomentum,
    VolatilityBreakout.name: VolatilityBreakout,
    # funding_carry is deliberately NOT here: it requires a funding series at
    # construction, which name-based CLIs cannot supply. Research code
    # constructs it directly; walk-forward uses strategy_factory.
}


def make_strategy(name: str, params: dict | None = None) -> BaseStrategy:
    try:
        cls = STRATEGY_REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"Unknown strategy {name!r}. Implemented: {sorted(STRATEGY_REGISTRY)}"
        ) from None
    return cls(params)
