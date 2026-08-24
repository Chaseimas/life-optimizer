"""Config loading and the live-trading gates."""

from __future__ import annotations

import pytest

from trading_bot.core.config import (
    LIVE_CONFIRM_PHRASE,
    ConfigError,
    build_config,
    load_config,
)


def test_default_config_is_paper_and_live_disabled(config):
    assert config.execution.mode == "paper"
    assert config.execution.live.enabled is False
    assert config.live_trading_allowed is False


def test_default_config_has_sane_risk_limits(config):
    r = config.risk
    assert r.max_daily_loss > 0
    assert 0 < r.max_risk_per_trade <= 0.05
    assert r.max_position_size > 0
    assert r.max_trades_per_day >= 1
    assert 0 < r.max_drawdown < 1
    assert r.max_open_exposure > 0
    assert r.max_consecutive_losses >= 1


def test_hyperliquid_disabled_by_default(config):
    hl = config.venues["hyperliquid"]
    assert hl["enabled"] is False
    assert hl["us_compliant_access"] is False


def test_live_mode_without_enable_flag_rejected(default_raw):
    default_raw["execution"]["mode"] = "live"
    with pytest.raises(ConfigError, match="live.enabled"):
        build_config(default_raw)


def test_live_mode_without_confirm_phrase_rejected(default_raw):
    default_raw["execution"]["mode"] = "live"
    default_raw["execution"]["live"] = {"enabled": True, "confirm_phrase": "yes please"}
    with pytest.raises(ConfigError, match="confirm_phrase"):
        build_config(default_raw)


def test_live_mode_with_full_arming_builds(default_raw):
    default_raw["execution"]["mode"] = "live"
    default_raw["execution"]["live"] = {
        "enabled": True,
        "confirm_phrase": LIVE_CONFIRM_PHRASE,
    }
    cfg = build_config(default_raw)
    assert cfg.live_trading_allowed is True  # config armed; executors still refuse (Phase 15)


def test_missing_risk_limit_rejected(default_raw):
    del default_raw["risk"]["max_daily_loss"]
    with pytest.raises(ConfigError, match="max_daily_loss"):
        build_config(default_raw)


def test_excessive_risk_per_trade_rejected(default_raw):
    default_raw["risk"]["max_risk_per_trade"] = 0.10  # 10% per trade: never
    with pytest.raises(ConfigError, match="max_risk_per_trade"):
        build_config(default_raw)


def test_invalid_mode_rejected(default_raw):
    default_raw["execution"]["mode"] = "yolo"
    with pytest.raises(ConfigError, match="mode"):
        build_config(default_raw)


def test_missing_config_file_raises():
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent/config.yaml")
