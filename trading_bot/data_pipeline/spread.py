"""Synthetic cross-market spread instrument (Pass 4, EXPLORATORY).

Builds a tradeable-in-simulation representation of a market-neutral pair —
long numerator / short denominator (e.g. ETH/BTC) — so relative-value ideas
can run through the SAME engine, risk manager, and cost machinery as
everything else.

Construction: spread index S = scale * (P_num / P_den). A position of size s
carries notional S*s dollars PER LEG; a 1% ratio move is 1% of that
notional, exactly like a linear perp on the ratio. Costs are configured at
TWO-LEG rates (double fees, double slippage); funding is the NET of the two
legs (long numerator pays f_num, short denominator receives f_den).

HONEST LIMITATIONS (read before trusting anything built on this):
1. Intrabar ratio extremes are unobservable from per-leg OHLC. The bars use
   BOUNDS: high = h_num/l_den (extremes coinciding), low = l_num/h_den.
   Stops therefore trigger MORE often than reality — conservative for a
   stop-based system — but true intrabar spread paths remain unknown.
2. Two-leg execution risk (one leg fills, the other doesn't) is NOT modeled.
   Real pair execution is strictly worse than this simulation.
3. Volume is the per-bar minimum of the legs' volumes — a liquidity
   indicator only, not a tradeable quantity.
Results on this instrument are exploratory and form an OPTIMISTIC bound on
practicality (costs aside, which are modeled at full two-leg rates).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_bot.core.market import FeeMode, FeeSpec, MarketSpec, SessionSpec
from trading_bot.core.types import Venue
from trading_bot.data_pipeline.frames import ensure_canonical

DEFAULT_SCALE = 100_000.0


def build_spread_frame(num: pd.DataFrame, den: pd.DataFrame,
                       scale: float = DEFAULT_SCALE) -> pd.DataFrame:
    """Spread bars from two aligned canonical leg frames (inner join)."""
    num = ensure_canonical(num)
    den = ensure_canonical(den)
    idx = num.index.intersection(den.index)
    if len(idx) < 10:
        raise ValueError("legs share fewer than 10 timestamps")
    n, d = num.loc[idx], den.loc[idx]
    o = scale * n["open"] / d["open"]
    c = scale * n["close"] / d["close"]
    hi_bound = scale * n["high"] / d["low"]     # upper BOUND on intrabar ratio
    lo_bound = scale * n["low"] / d["high"]     # lower BOUND
    out = pd.DataFrame({
        "open": o,
        "high": np.maximum.reduce([hi_bound.to_numpy(), o.to_numpy(), c.to_numpy()]),
        "low": np.minimum.reduce([lo_bound.to_numpy(), o.to_numpy(), c.to_numpy()]),
        "close": c,
        "volume": np.minimum(n["volume"].to_numpy(), d["volume"].to_numpy()),
    }, index=idx)
    return ensure_canonical(out)


def spread_market_spec(
    market_id: str = "SPREAD:ETH-BTC",
    *,
    leg_taker: float = 0.00045,
    leg_maker: float = 0.00015,
) -> MarketSpec:
    """Spec with TWO-LEG costs baked into the fee rates."""
    return MarketSpec(
        market_id=market_id,
        venue=Venue.SYNTHETIC,
        symbol=market_id,
        description="Synthetic pair spread (two-leg costs; see data_pipeline/spread.py caveats)",
        tick_size=0.01,
        point_value=1.0,
        size_step=0.0001,
        min_size=0.0001,
        min_notional=20.0,            # >= venue minimum on each leg
        fees=FeeSpec(mode=FeeMode.BPS_NOTIONAL,
                     taker=2 * leg_taker, maker=2 * leg_maker),
        session=SessionSpec(is_24_7=True, timezone="UTC",
                            notes="synthetic pair; two-leg execution risk NOT modeled"),
        has_funding=True,
        funding_interval_hours=1.0,
    )


def net_funding(f_num: pd.Series, f_den: pd.Series) -> pd.Series:
    """Funding paid by long-numerator/short-denominator: f_num - f_den on
    shared timestamps (positive = the spread position pays)."""
    idx = f_num.index.intersection(f_den.index)
    return (f_num.loc[idx] - f_den.loc[idx]).rename("funding_rate").sort_index()
