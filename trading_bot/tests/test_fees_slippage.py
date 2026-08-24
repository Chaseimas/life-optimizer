"""Fee and slippage models: costs are always paid, always adverse."""

from __future__ import annotations

import pytest

from trading_bot.backtesting.fees import fee_for_fill, round_trip_fee
from trading_bot.backtesting.slippage import BpsSlippage, FixedTicksSlippage
from trading_bot.core.market import get_market
from trading_bot.core.types import Liquidity

MNQ = get_market("MNQ")
BTC = get_market("HL:BTC")


def test_mnq_per_contract_fee():
    assert fee_for_fill(MNQ, 20000.0, 2) == pytest.approx(2.48)  # 2 * 1.24


def test_hyperliquid_bps_fee_taker_vs_maker():
    # 0.01 BTC @ 60,000 = $600 notional
    assert fee_for_fill(BTC, 60000.0, 0.01, Liquidity.TAKER) == pytest.approx(0.27)   # 4.5 bps
    assert fee_for_fill(BTC, 60000.0, 0.01, Liquidity.MAKER) == pytest.approx(0.09)   # 1.5 bps


def test_round_trip_fee():
    assert round_trip_fee(MNQ, 20000.0, 20010.0, 1) == pytest.approx(2.48)


def test_zero_size_zero_fee():
    assert fee_for_fill(MNQ, 20000.0, 0) == 0.0


def test_fixed_ticks_slippage_adverse_both_ways():
    model = FixedTicksSlippage(ticks=1)
    assert model.fill_price(MNQ, +1, 20000.00, 1) == pytest.approx(20000.25)  # buy pays up
    assert model.fill_price(MNQ, -1, 20000.00, 1) == pytest.approx(19999.75)  # sell gets less


def test_bps_slippage_adverse_both_ways():
    model = BpsSlippage(bps=5)
    buy = model.fill_price(BTC, +1, 60000.0, 0.1)
    sell = model.fill_price(BTC, -1, 60000.0, 0.1)
    assert buy == pytest.approx(60030.0)
    assert sell == pytest.approx(59970.0)


def test_slippage_rejects_bad_direction():
    with pytest.raises(ValueError):
        FixedTicksSlippage(1).fill_price(MNQ, 0, 20000.0, 1)


def test_negative_costs_rejected():
    with pytest.raises(ValueError):
        FixedTicksSlippage(-1)
    with pytest.raises(ValueError):
        BpsSlippage(-0.1)
