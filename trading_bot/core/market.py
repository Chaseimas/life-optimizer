"""Market abstraction: venue-agnostic contract specifications.

Strategies never see a venue. They see a ``MarketSpec`` that answers:
tick size, value of one price point, size granularity, fees, session,
funding mechanics. The same strategy can therefore run on MNQ, BTC perps,
ETH perps, etc. without modification.

NOTE ON DEFAULT NUMBERS: fee and precision defaults below are reasonable
research estimates. Before paper/live trading (Phases 13+):
* CME fees must be verified against your actual broker's commission schedule.
* Hyperliquid tick/size precision must be pulled from the live exchange
  metadata API (it changes with price levels), and fees from your fee tier.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum

from trading_bot.core.types import Liquidity, Side, Venue


class FeeMode(str, Enum):
    PER_CONTRACT = "per_contract"  # flat currency per contract per side (futures)
    BPS_NOTIONAL = "bps_notional"  # fraction of traded notional (perps)


@dataclass(frozen=True)
class FeeSpec:
    mode: FeeMode
    taker: float  # PER_CONTRACT: currency/contract/side. BPS_NOTIONAL: fraction (0.00045 = 4.5 bps)
    maker: float

    def rate(self, liquidity: Liquidity) -> float:
        return self.taker if liquidity is Liquidity.TAKER else self.maker


@dataclass(frozen=True)
class SessionSpec:
    is_24_7: bool
    timezone: str
    notes: str = ""


@dataclass(frozen=True)
class MarketSpec:
    market_id: str          # internal id, e.g. "MNQ" or "HL:BTC"
    venue: Venue
    symbol: str             # venue-native symbol
    description: str
    tick_size: float        # minimum price increment
    point_value: float      # currency value of a 1.0 price move per contract/coin
    size_step: float        # order size granularity (1 contract for MNQ, fractional coins for HL)
    min_size: float
    min_notional: float     # venue minimum order notional (0 if none)
    fees: FeeSpec
    session: SessionSpec
    has_funding: bool = False
    funding_interval_hours: float | None = None

    # ---- price / size arithmetic -------------------------------------------------
    @property
    def tick_value(self) -> float:
        return self.tick_size * self.point_value

    def round_price(self, price: float) -> float:
        """Round to the nearest valid tick."""
        return round(round(price / self.tick_size) * self.tick_size, 12)

    def is_valid_price(self, price: float) -> bool:
        return abs(price - self.round_price(price)) <= self.tick_size * 1e-6

    def round_size(self, size: float) -> float:
        """Round size DOWN to the venue's size step. Never rounds up (never
        risks more than intended)."""
        if size <= 0:
            return 0.0
        steps = math.floor(size / self.size_step + 1e-9)
        return round(steps * self.size_step, 12)

    def is_valid_size(self, size: float) -> bool:
        return size >= self.min_size and abs(size - self.round_size(size)) <= self.size_step * 1e-6

    def notional(self, price: float, size: float) -> float:
        """Currency exposure of ``size`` units at ``price``."""
        return abs(price * self.point_value * size)

    def pnl(self, side: Side, entry: float, exit: float, size: float) -> float:
        """Gross P&L in account currency (fees/funding accounted separately)."""
        return (exit - entry) * int(side) * self.point_value * size


# ---- CME Globex session (MNQ) ---------------------------------------------------
_CME_SESSION = SessionSpec(
    is_24_7=False,
    timezone="America/Chicago",
    notes=(
        "Globex: Sun 17:00 CT to Fri 16:00 CT with a daily maintenance halt "
        "16:00-17:00 CT. Holiday calendar and early closes handled in Phase 3."
    ),
)

_HL_SESSION = SessionSpec(is_24_7=True, timezone="UTC", notes="Perpetuals trade 24/7.")

# Hyperliquid base-tier fees (VERIFY against your fee tier before Phase 13):
_HL_FEES = FeeSpec(mode=FeeMode.BPS_NOTIONAL, taker=0.00045, maker=0.00015)

_MARKETS: dict[str, MarketSpec] = {
    "MNQ": MarketSpec(
        market_id="MNQ",
        venue=Venue.CME,
        symbol="MNQ",
        description="CME Micro E-mini Nasdaq-100 futures",
        tick_size=0.25,
        point_value=2.0,     # $2 per index point -> tick value $0.50
        size_step=1.0,       # whole contracts only
        min_size=1.0,
        min_notional=0.0,
        # All-in commission + exchange fees per contract per side. Broker
        # dependent — this is a conservative research default, VERIFY.
        fees=FeeSpec(mode=FeeMode.PER_CONTRACT, taker=1.24, maker=1.24),
        session=_CME_SESSION,
        has_funding=False,
    ),
    "HL:BTC": MarketSpec(
        market_id="HL:BTC",
        venue=Venue.HYPERLIQUID,
        symbol="BTC",
        description="Hyperliquid BTC-USD perpetual",
        tick_size=1.0,        # approximation of HL's 5-significant-figure rule at current prices
        point_value=1.0,      # linear perp sized in coins
        size_step=0.00001,
        min_size=0.00001,
        min_notional=10.0,
        fees=_HL_FEES,
        session=_HL_SESSION,
        has_funding=True,
        funding_interval_hours=1.0,  # paid hourly (rate quoted on an 8h basis)
    ),
    "HL:ETH": MarketSpec(
        market_id="HL:ETH",
        venue=Venue.HYPERLIQUID,
        symbol="ETH",
        description="Hyperliquid ETH-USD perpetual",
        tick_size=0.1,
        point_value=1.0,
        size_step=0.0001,
        min_size=0.0001,
        min_notional=10.0,
        fees=_HL_FEES,
        session=_HL_SESSION,
        has_funding=True,
        funding_interval_hours=1.0,
    ),
    "SYNTH": MarketSpec(
        market_id="SYNTH",
        venue=Venue.SYNTHETIC,
        symbol="SYNTH",
        description="Synthetic random-walk instrument for pipeline testing only (untradeable)",
        tick_size=0.25,
        point_value=1.0,
        size_step=0.01,
        min_size=0.01,
        min_notional=10.0,
        fees=FeeSpec(mode=FeeMode.BPS_NOTIONAL, taker=0.00045, maker=0.00015),
        session=SessionSpec(is_24_7=True, timezone="UTC", notes="synthetic, 24/7"),
        has_funding=False,
    ),
    "HL:SOL": MarketSpec(
        market_id="HL:SOL",
        venue=Venue.HYPERLIQUID,
        symbol="SOL",
        description="Hyperliquid SOL-USD perpetual",
        tick_size=0.01,
        point_value=1.0,
        size_step=0.01,
        min_size=0.01,
        min_notional=10.0,
        fees=_HL_FEES,
        session=_HL_SESSION,
        has_funding=True,
        funding_interval_hours=1.0,
    ),
}


def list_markets() -> list[str]:
    return sorted(_MARKETS)


def get_market(market_id: str, config=None) -> MarketSpec:
    """Look up a market spec, optionally applying fee overrides from config.

    ``config`` is a ``trading_bot.core.config.Config`` (kept untyped here to
    avoid a circular import).
    """
    try:
        spec = _MARKETS[market_id]
    except KeyError:
        raise KeyError(
            f"Unknown market {market_id!r}. Known markets: {list_markets()}"
        ) from None

    if config is not None:
        venue_cfg = config.venues.get(spec.venue.value, {})
        fee_over = venue_cfg.get("fees", {}) if isinstance(venue_cfg, dict) else {}
        if spec.fees.mode is FeeMode.PER_CONTRACT and "commission_per_side" in fee_over:
            c = float(fee_over["commission_per_side"])
            spec = replace(spec, fees=FeeSpec(FeeMode.PER_CONTRACT, taker=c, maker=c))
        elif spec.fees.mode is FeeMode.BPS_NOTIONAL and (
            "taker" in fee_over or "maker" in fee_over
        ):
            spec = replace(
                spec,
                fees=FeeSpec(
                    FeeMode.BPS_NOTIONAL,
                    taker=float(fee_over.get("taker", spec.fees.taker)),
                    maker=float(fee_over.get("maker", spec.fees.maker)),
                ),
            )
    return spec
