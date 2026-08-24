"""Execution gates: live trading locked, Hyperliquid compliance-gated,
order validation, kill-switch enforcement on the submit path."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trading_bot.core.config import LIVE_CONFIRM_PHRASE, build_config
from trading_bot.core.events import Order
from trading_bot.core.market import get_market
from trading_bot.core.types import ExecutionMode, OrderType, Side
from trading_bot.execution.base_executor import (
    ComplianceGate,
    ExecutorError,
    LiveTradingDisabled,
    OrderValidationError,
)
from trading_bot.execution.hyperliquid_executor import HyperliquidExecutor
from trading_bot.execution.mnq_executor import MNQExecutor
from trading_bot.risk.kill_switch import KillSwitch, KillSwitchReason, KillSwitchTripped

TS = datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)


def armed_live_config(default_raw, *, hl_enabled=False, hl_compliant=False):
    default_raw["execution"]["mode"] = "live"
    default_raw["execution"]["live"] = {"enabled": True, "confirm_phrase": LIVE_CONFIRM_PHRASE}
    default_raw["venues"]["hyperliquid"]["enabled"] = hl_enabled
    default_raw["venues"]["hyperliquid"]["us_compliant_access"] = hl_compliant
    return build_config(default_raw)


# ---- live gates -----------------------------------------------------------------
def test_live_mode_refused_with_default_config(config):
    with pytest.raises(LiveTradingDisabled):
        MNQExecutor(get_market("MNQ"), config, KillSwitch(), ExecutionMode.LIVE)


def test_live_mnq_not_implemented_even_when_armed(default_raw):
    cfg = armed_live_config(default_raw)
    # Config fully armed -> the gate passes, but live routing is Phase 15.
    with pytest.raises(NotImplementedError, match="Phase 15"):
        MNQExecutor(get_market("MNQ"), cfg, KillSwitch(), ExecutionMode.LIVE)


def test_live_hyperliquid_requires_venue_enabled(default_raw):
    cfg = armed_live_config(default_raw, hl_enabled=False)
    with pytest.raises(LiveTradingDisabled, match="hyperliquid.enabled"):
        HyperliquidExecutor(get_market("HL:BTC"), cfg, KillSwitch(), ExecutionMode.LIVE)


def test_live_hyperliquid_compliance_gate(default_raw):
    cfg = armed_live_config(default_raw, hl_enabled=True, hl_compliant=False)
    with pytest.raises(ComplianceGate, match="compliant"):
        HyperliquidExecutor(get_market("HL:BTC"), cfg, KillSwitch(), ExecutionMode.LIVE)


def test_live_hyperliquid_not_implemented_even_when_fully_armed(default_raw):
    cfg = armed_live_config(default_raw, hl_enabled=True, hl_compliant=True)
    with pytest.raises(NotImplementedError, match="Phase 15"):
        HyperliquidExecutor(get_market("HL:BTC"), cfg, KillSwitch(), ExecutionMode.LIVE)


def test_paper_mode_constructs_fine(config):
    MNQExecutor(get_market("MNQ"), config, KillSwitch(), ExecutionMode.PAPER)
    HyperliquidExecutor(get_market("HL:BTC"), config, KillSwitch(), ExecutionMode.PAPER)


def test_executor_rejects_wrong_venue_market(config):
    with pytest.raises(ExecutorError, match="venue"):
        MNQExecutor(get_market("HL:BTC"), config, KillSwitch(), ExecutionMode.PAPER)


# ---- order validation -----------------------------------------------------------
@pytest.fixture()
def mnq_paper(config):
    return MNQExecutor(get_market("MNQ"), config, KillSwitch(), ExecutionMode.PAPER)


def test_fractional_mnq_contracts_rejected(mnq_paper):
    order = Order(ts=TS, market_id="MNQ", side=Side.LONG, qty=1.5)
    with pytest.raises(OrderValidationError, match="size step"):
        mnq_paper.validate_order(order)


def test_off_tick_limit_price_rejected(mnq_paper):
    order = Order(
        ts=TS, market_id="MNQ", side=Side.LONG, qty=1,
        order_type=OrderType.LIMIT, limit_price=20000.30,
    )
    with pytest.raises(OrderValidationError, match="tick grid"):
        mnq_paper.validate_order(order)


def test_off_tick_stop_loss_rejected(mnq_paper):
    order = Order(ts=TS, market_id="MNQ", side=Side.LONG, qty=1, stop_loss=19987.13)
    with pytest.raises(OrderValidationError, match="tick grid"):
        mnq_paper.validate_order(order)


def test_zero_qty_rejected(mnq_paper):
    order = Order(ts=TS, market_id="MNQ", side=Side.LONG, qty=0)
    with pytest.raises(OrderValidationError, match="qty"):
        mnq_paper.validate_order(order)


def test_valid_order_passes_validation(mnq_paper):
    order = Order(
        ts=TS, market_id="MNQ", side=Side.SHORT, qty=2,
        order_type=OrderType.LIMIT, limit_price=20000.25,
        stop_loss=20050.00, take_profit=19900.75,
    )
    mnq_paper.validate_order(order)  # must not raise


def test_hyperliquid_min_notional_rejected(config):
    hl = HyperliquidExecutor(get_market("HL:BTC"), config, KillSwitch(), ExecutionMode.PAPER)
    order = Order(
        ts=TS, market_id="HL:BTC", side=Side.LONG, qty=0.0001,
        order_type=OrderType.LIMIT, limit_price=60000.0,  # $6 notional < $10 min
    )
    with pytest.raises(OrderValidationError, match="minimum"):
        hl.validate_order(order)


# ---- kill switch on the submit path --------------------------------------------
def test_submit_blocked_by_kill_switch(config):
    ks = KillSwitch()
    ex = MNQExecutor(get_market("MNQ"), config, ks, ExecutionMode.PAPER)
    ks.trip(KillSwitchReason.STALE_PRICES, "no tick for 60s")
    order = Order(ts=TS, market_id="MNQ", side=Side.LONG, qty=1)
    with pytest.raises(KillSwitchTripped):
        ex.submit_order(order)


def test_submit_without_routing_raises_not_implemented(config):
    # Paper ROUTING doesn't exist until Phases 5/13 — an honest error, not a fake fill.
    ex = MNQExecutor(get_market("MNQ"), config, KillSwitch(), ExecutionMode.PAPER)
    order = Order(ts=TS, market_id="MNQ", side=Side.LONG, qty=1)
    with pytest.raises(NotImplementedError):
        ex.submit_order(order)
