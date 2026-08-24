"""Position sizing: risk-based, always rounds down, every cap enforced."""

from __future__ import annotations

import pytest

from trading_bot.core.config import RiskLimits
from trading_bot.core.market import get_market
from trading_bot.risk.position_sizing import compute_position_size


def limits(**overrides) -> RiskLimits:
    base = dict(
        max_daily_loss=300.0,
        max_risk_per_trade=0.005,
        max_position_size=3,
        max_trades_per_day=8,
        max_drawdown=0.10,
        max_open_exposure=1_000_000.0,
        max_consecutive_losses=3,
    )
    base.update(overrides)
    return RiskLimits(**base)


def test_mnq_risk_based_size():
    # $100k equity, 0.5% risk = $500. Stop 25 points on MNQ = $50/contract
    # -> raw 10 contracts, capped at max_position_size 3.
    r = compute_position_size(
        equity=100_000, price=20_000, stop_distance=25,
        spec=get_market("MNQ"), limits=limits(),
    )
    assert r.size == 3
    assert r.risk_amount == pytest.approx(500.0)
    assert "max_position_size" in r.capped_by


def test_mnq_uncapped_size_floor():
    # $10k equity, 0.5% = $50 risk; stop 30 pts = $60/contract -> raw 0.833 -> 0.
    r = compute_position_size(
        equity=10_000, price=20_000, stop_distance=30,
        spec=get_market("MNQ"), limits=limits(),
    )
    assert r.size == 0
    assert "below venue minimum" in r.reason


def test_exposure_cap():
    # MNQ notional at 20k = $40k/contract; exposure cap $60k -> max 1 contract.
    r = compute_position_size(
        equity=1_000_000, price=20_000, stop_distance=25,
        spec=get_market("MNQ"), limits=limits(max_open_exposure=60_000, max_position_size=100),
    )
    assert r.size == 1
    assert "max_open_exposure" in r.capped_by


def test_existing_exposure_reduces_budget():
    r = compute_position_size(
        equity=1_000_000, price=20_000, stop_distance=25,
        spec=get_market("MNQ"),
        limits=limits(max_open_exposure=60_000, max_position_size=100),
        current_open_exposure=60_000,
    )
    assert r.size == 0
    assert "exposure budget exhausted" in r.reason


def test_no_stop_no_trade():
    r = compute_position_size(
        equity=100_000, price=20_000, stop_distance=0,
        spec=get_market("MNQ"), limits=limits(),
    )
    assert r.size == 0
    assert "stop" in r.reason


def test_negative_equity_no_trade():
    r = compute_position_size(
        equity=-5.0, price=20_000, stop_distance=25,
        spec=get_market("MNQ"), limits=limits(),
    )
    assert r.size == 0


def test_hyperliquid_fractional_size():
    # $50k equity, 0.5% = $250 risk; stop $500 on BTC -> 0.5 BTC.
    r = compute_position_size(
        equity=50_000, price=60_000, stop_distance=500,
        spec=get_market("HL:BTC"), limits=limits(),
    )
    assert r.size == pytest.approx(0.5)
    assert r.notional == pytest.approx(30_000.0)


def test_hyperliquid_min_notional_blocks_dust():
    # $100 equity, 0.5% = $0.50 risk; stop $5000 -> 0.0001 BTC -> $6 notional < $10 min.
    r = compute_position_size(
        equity=100, price=60_000, stop_distance=5_000,
        spec=get_market("HL:BTC"), limits=limits(),
    )
    assert r.size == 0
    assert "notional below venue minimum" in r.reason


def test_risk_per_trade_cannot_exceed_limit():
    # Caller asks for 5% but the limit is 0.5% — the limit wins.
    r = compute_position_size(
        equity=100_000, price=20_000, stop_distance=25,
        spec=get_market("MNQ"), limits=limits(max_position_size=1000),
        risk_per_trade=0.05,
    )
    assert r.risk_amount == pytest.approx(500.0)  # 0.5%, not 5%
