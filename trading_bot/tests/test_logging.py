"""Logging: file + console handlers, UTC timestamps, idempotent setup."""

from __future__ import annotations

import logging

import pytest

from trading_bot.monitoring.logging import ROOT_LOGGER_NAME, get_logger, setup_logging


@pytest.fixture()
def clean_logger():
    """Reset the singleton root logger around each test."""
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    saved = logger.handlers[:]
    logger.handlers.clear()
    if hasattr(logger, "_trading_bot_configured"):
        del logger._trading_bot_configured
    yield logger
    for h in logger.handlers:
        h.close()
    logger.handlers = saved
    logger._trading_bot_configured = bool(saved)


def test_writes_to_log_file(tmp_path, clean_logger):
    setup_logging(level="DEBUG", log_dir=tmp_path, console=False)
    get_logger("unit").info("hello from the test")
    for h in clean_logger.handlers:
        h.flush()
    content = (tmp_path / "trading_bot.log").read_text()
    assert "hello from the test" in content
    assert "trading_bot.unit" in content
    assert "INFO" in content


def test_setup_is_idempotent(tmp_path, clean_logger):
    setup_logging(level="INFO", log_dir=tmp_path, console=False)
    n = len(clean_logger.handlers)
    setup_logging(level="INFO", log_dir=tmp_path, console=False)
    assert len(clean_logger.handlers) == n


def test_child_logger_naming():
    assert get_logger("risk").name == "trading_bot.risk"
    assert get_logger().name == "trading_bot"


def test_respects_level(tmp_path, clean_logger):
    setup_logging(level="WARNING", log_dir=tmp_path, console=False)
    get_logger("unit").info("should not appear")
    get_logger("unit").warning("should appear")
    for h in clean_logger.handlers:
        h.flush()
    content = (tmp_path / "trading_bot.log").read_text()
    assert "should not appear" not in content
    assert "should appear" in content
