"""Central logging setup.

* UTC timestamps everywhere (trading systems must never log in ambiguous
  local time).
* Console + rotating file handler under ``trading_bot/logs/``.
* Idempotent: calling ``setup_logging`` twice never duplicates handlers.

Usage:
    from trading_bot.core.config import load_config
    from trading_bot.monitoring.logging import setup_logging, get_logger

    cfg = load_config()
    setup_logging(cfg)
    log = get_logger("research")
    log.info("hello")
"""

from __future__ import annotations

import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT_LOGGER_NAME = "trading_bot"
_LOG_FORMAT = "%(asctime)s.%(msecs)03dZ | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def setup_logging(config=None, *, level: str | None = None, log_dir: str | Path | None = None,
                  console: bool | None = None) -> logging.Logger:
    """Configure the ``trading_bot`` root logger.

    Accepts a ``Config`` (uses its logging section) or explicit overrides.
    """
    if config is not None:
        level = level or config.logging.level
        log_dir = log_dir or config.resolve(config.logging.dir)
        console = config.logging.console if console is None else console
    level = (level or "INFO").upper()
    console = True if console is None else console

    logger = logging.getLogger(ROOT_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    if getattr(logger, "_trading_bot_configured", False):
        return logger

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
    formatter.converter = time.gmtime  # UTC

    if console:
        sh = logging.StreamHandler()
        sh.setFormatter(formatter)
        logger.addHandler(sh)

    if log_dir is not None:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            log_path / "trading_bot.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    logger._trading_bot_configured = True  # type: ignore[attr-defined]
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a child logger, e.g. ``get_logger("risk")`` -> ``trading_bot.risk``."""
    if not name:
        return logging.getLogger(ROOT_LOGGER_NAME)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
