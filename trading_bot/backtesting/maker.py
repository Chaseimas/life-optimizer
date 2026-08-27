"""Maker (limit-order) execution simulation for the backtest engine.

WHAT THIS MODELS
----------------
Entries via resting limit orders instead of marketable (taker) orders:

* On a signal, a limit order is placed at the next bar's open, offset by
  ``limit_offset_bps`` in the passive direction (buy below, sell above).
* The order rests for up to ``max_lifetime_bars`` bars, is evaluated against
  each bar's OHLC, and can end in exactly one of: FULL fill, PARTIAL fill,
  cancel-by-risk, or EXPIRY (a missed trade stays missed).
* Filled entries pay the MAKER fee; a fill price can never be better than the
  limit (buys fill at the limit or on a gap through it, still at the limit).
* Exits remain TAKER (protective stops and signal exits are marketable by
  design: an exit that might not fill is not an exit). The maker benefit in
  this system is therefore entry-side only — round-trip cost drops from
  ~11 bps (taker+taker) to ~7 bps (maker entry + taker exit + exit
  slippage), NOT to 3 bps. That is deliberate honesty, not a bug.

WHAT OHLC DATA CANNOT TELL US (read before trusting any number)
---------------------------------------------------------------
OHLC bars contain no queue position, no trade tape, no book depth. Three
approximations are therefore unavoidable, and each is surfaced as an explicit
assumption instead of silently baked in:

1. QUEUE POSITION IS UNKNOWABLE. If a bar merely TOUCHES the limit price, a
   real order may or may not have filled (depends on queue depth and how much
   volume printed at that level). ``fill_on`` selects the assumption:
     - "through": fill ONLY if price trades strictly beyond the limit by
       ``penetration_bps`` (everyone at the level was swept). Conservative;
       understates fills.
     - "touch":   fill on any touch. Optimistic UPPER BOUND; overstates
       fills. Never draw conclusions from this mode alone.
     - "prob":    swept -> full fill; touched-but-not-swept -> fill with
       probability ``touch_fill_prob`` at fraction ``partial_fill_frac``
       (seeded RNG -> deterministic runs).
2. ADVERSE SELECTION IS STRUCTURAL AND PARTIAL. Passive fills happen
   disproportionately when price is moving against the order — the model
   captures the first-order effect mechanically (a buy limit fills only when
   price falls to it). What OHLC cannot capture is latency/queue toxicity
   (you fill just before the level breaks). ``adverse_selection_bps`` adds an
   explicit per-fill cash cost (notional * bps) as compensation; it is
   accounted in the trade's slippage_cost and subtracted from net P&L.
3. INTRABAR PATH IS UNKNOWN. Whether the limit filled before or after the
   bar's extreme is unknowable; the engine keeps its conservative existing
   convention (a same-bar protective stop can trigger after the fill).

Anything this module reports is conditional on these assumptions. The
research protocol runs conservative / baseline / optimistic scenarios and
never concludes from the optimistic one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from trading_bot.core.events import Bar
from trading_bot.core.market import MarketSpec
from trading_bot.core.types import Side

FILL_MODES = ("through", "touch", "prob")


@dataclass(frozen=True)
class MakerParams:
    limit_offset_bps: float = 0.0      # passive offset from next-bar open (0 = join the open)
    max_lifetime_bars: int = 3         # cancel after this many bars unfilled
    fill_on: str = "prob"              # "through" | "touch" | "prob"  (see module docstring)
    penetration_bps: float = 1.0       # "swept" means trading beyond limit by this much
    touch_fill_prob: float = 0.5       # prob mode: P(fill | touched but not swept)
    partial_fill_frac: float = 1.0     # fraction filled on touch fills (swept -> always full)
    min_fill_frac: float = 0.1         # ignore fills smaller than this fraction
    adverse_selection_bps: float = 0.0 # explicit per-fill cash cost, notional * bps
    seed: int = 7                      # RNG seed (prob mode) -> deterministic runs

    def validate(self) -> None:
        if self.fill_on not in FILL_MODES:
            raise ValueError(f"fill_on must be one of {FILL_MODES}")
        if self.limit_offset_bps < 0 or self.penetration_bps < 0:
            raise ValueError("offsets must be >= 0")
        if self.max_lifetime_bars < 1:
            raise ValueError("max_lifetime_bars must be >= 1")
        if not (0.0 <= self.touch_fill_prob <= 1.0):
            raise ValueError("touch_fill_prob must be in [0, 1]")
        if not (0.0 < self.partial_fill_frac <= 1.0):
            raise ValueError("partial_fill_frac must be in (0, 1]")
        if not (0.0 < self.min_fill_frac <= 1.0):
            raise ValueError("min_fill_frac must be in (0, 1]")
        if self.adverse_selection_bps < 0:
            raise ValueError("adverse_selection_bps must be >= 0")

    def describe(self) -> dict:
        """For experiment logs — every assumption, visible."""
        return {
            "execution": "maker_entry_taker_exit",
            "limit_offset_bps": self.limit_offset_bps,
            "max_lifetime_bars": self.max_lifetime_bars,
            "fill_on": self.fill_on,
            "penetration_bps": self.penetration_bps,
            "touch_fill_prob": self.touch_fill_prob,
            "partial_fill_frac": self.partial_fill_frac,
            "min_fill_frac": self.min_fill_frac,
            "adverse_selection_bps": self.adverse_selection_bps,
            "seed": self.seed,
        }


# Three named research scenarios. Conclusions come from conservative/baseline;
# optimistic exists only to bound the best case.
SCENARIOS: dict[str, MakerParams] = {
    "maker_conservative": MakerParams(
        fill_on="through", penetration_bps=1.0, max_lifetime_bars=2,
        adverse_selection_bps=0.5,
    ),
    "maker_baseline": MakerParams(
        fill_on="prob", touch_fill_prob=0.5, penetration_bps=1.0,
        max_lifetime_bars=3, adverse_selection_bps=0.25,
    ),
    "maker_optimistic": MakerParams(
        fill_on="touch", max_lifetime_bars=5, adverse_selection_bps=0.0,
    ),
}


@dataclass
class RestingOrder:
    """A live simulated limit order (entry only; exits are taker)."""

    direction: Side
    limit_price: float
    size: float                 # planned size (from risk sizing at placement)
    stop_distance: float
    tp_distance: float | None
    placed_ts: datetime
    reason: str                 # originating signal reason
    bars_alive: int = 0


@dataclass(frozen=True)
class FillEvent:
    price: float                # always the limit price (never better than limit)
    fraction: float             # (0, 1]; 1.0 = full fill
    swept: bool                 # price traded through the level (fill is certain)


def limit_price_for(spec: MarketSpec, direction: Side, ref_open: float,
                    params: MakerParams) -> float:
    """Passive limit off the reference open: buys below, sells above."""
    off = params.limit_offset_bps / 10_000.0
    raw = ref_open * (1.0 - off) if direction is Side.LONG else ref_open * (1.0 + off)
    return spec.round_price(raw)


def evaluate_fill(bar: Bar, direction: Side, limit_price: float,
                  params: MakerParams, rng: np.random.Generator) -> FillEvent | None:
    """Evaluate one bar against a resting limit order. Returns a FillEvent or
    None (order keeps resting). Deterministic given the rng state."""
    pen = limit_price * params.penetration_bps / 10_000.0
    if direction is Side.LONG:
        gapped = bar.open < limit_price
        swept = gapped or bar.low < limit_price - pen
        touched = bar.low <= limit_price
    else:
        gapped = bar.open > limit_price
        swept = gapped or bar.high > limit_price + pen
        touched = bar.high >= limit_price

    if params.fill_on == "through":
        return FillEvent(limit_price, 1.0, True) if swept else None
    if params.fill_on == "touch":
        return FillEvent(limit_price, 1.0, swept) if touched else None
    # prob mode
    if swept:
        return FillEvent(limit_price, 1.0, True)
    if touched and rng.random() < params.touch_fill_prob:
        frac = params.partial_fill_frac
        if frac < params.min_fill_frac:
            return None
        return FillEvent(limit_price, frac, False)
    return None


def adverse_selection_cost(spec: MarketSpec, price: float, size: float,
                           params: MakerParams) -> float:
    """Explicit cash charge per fill compensating for queue/latency toxicity
    OHLC cannot see. Accounted as slippage_cost and subtracted from net."""
    return spec.notional(price, size) * params.adverse_selection_bps / 10_000.0
