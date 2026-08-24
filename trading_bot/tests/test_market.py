"""Market specs: contract math, tick/size rounding, P&L, fee overrides."""

from __future__ import annotations

import pytest

from trading_bot.core.config import build_config
from trading_bot.core.market import FeeMode, get_market, list_markets
from trading_bot.core.types import Side


def test_registry_contains_required_markets():
    ids = list_markets()
    assert "MNQ" in ids
    assert "HL:BTC" in ids and "HL:ETH" in ids and "HL:SOL" in ids


def test_unknown_market_raises():
    with pytest.raises(KeyError, match="Unknown market"):
        get_market("DOGE:MOON")


def test_mnq_contract_spec():
    mnq = get_market("MNQ")
    assert mnq.tick_size == 0.25
    assert mnq.point_value == 2.0
    assert mnq.tick_value == 0.5
    assert mnq.size_step == 1.0
    assert mnq.has_funding is False
    assert mnq.session.is_24_7 is False
    assert mnq.session.timezone == "America/Chicago"


def test_mnq_pnl():
    mnq = get_market("MNQ")
    # Long 1 contract, +10 points => $20
    assert mnq.pnl(Side.LONG, 20000.0, 20010.0, 1) == pytest.approx(20.0)
    # Short 2 contracts, market rises 5 points => -$20
    assert mnq.pnl(Side.SHORT, 20000.0, 20005.0, 2) == pytest.approx(-20.0)


def test_mnq_price_rounding():
    mnq = get_market("MNQ")
    assert mnq.round_price(20000.13) == pytest.approx(20000.25)
    assert mnq.round_price(20000.10) == pytest.approx(20000.00)
    assert mnq.is_valid_price(20000.25)
    assert not mnq.is_valid_price(20000.30)


def test_mnq_size_rounding_never_rounds_up():
    mnq = get_market("MNQ")
    assert mnq.round_size(2.99) == 2.0
    assert mnq.round_size(0.4) == 0.0
    assert mnq.is_valid_size(1.0)
    assert not mnq.is_valid_size(1.5)


def test_mnq_notional():
    mnq = get_market("MNQ")
    # 20,000 index points * $2/point * 1 contract = $40,000
    assert mnq.notional(20000.0, 1) == pytest.approx(40000.0)


def test_hyperliquid_btc_spec():
    btc = get_market("HL:BTC")
    assert btc.session.is_24_7 is True
    assert btc.has_funding is True
    assert btc.funding_interval_hours == 1.0
    assert btc.point_value == 1.0
    assert btc.min_notional == 10.0
    assert btc.fees.mode is FeeMode.BPS_NOTIONAL


def test_hyperliquid_size_rounding():
    btc = get_market("HL:BTC")
    assert btc.round_size(0.123456789) == pytest.approx(0.12345)
    sol = get_market("HL:SOL")
    assert sol.round_size(3.999) == pytest.approx(3.99)


def test_hyperliquid_pnl_linear_perp():
    btc = get_market("HL:BTC")
    # Long 0.1 BTC, +1000 => $100
    assert btc.pnl(Side.LONG, 60000.0, 61000.0, 0.1) == pytest.approx(100.0)


def test_fee_override_from_config(default_raw):
    default_raw["venues"]["cme"]["fees"]["commission_per_side"] = 0.62
    default_raw["venues"]["hyperliquid"]["fees"]["taker"] = 0.0003
    cfg = build_config(default_raw)
    assert get_market("MNQ", cfg).fees.taker == pytest.approx(0.62)
    assert get_market("HL:BTC", cfg).fees.taker == pytest.approx(0.0003)
    # Without config: registry defaults
    assert get_market("MNQ").fees.taker == pytest.approx(1.24)
