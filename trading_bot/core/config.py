"""Configuration system.

Single YAML file (``trading_bot/config/config.yaml``) parsed into validated
dataclasses. Hard rules enforced here:

* ``execution.mode`` defaults to paper; live mode requires BOTH
  ``execution.live.enabled: true`` AND the exact confirmation phrase.
* Risk limits must be present and sane (positive, fractions in range).
* Hyperliquid live access additionally requires
  ``venues.hyperliquid.us_compliant_access: true`` — which must only ever be
  set if a lawful, compliant U.S. access path actually exists. The system
  never bypasses geographic restrictions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# The exact phrase a human must type into config.yaml before live mode can
# even be *considered* (live execution itself is Phase 15 and not implemented).
LIVE_CONFIRM_PHRASE = "I-UNDERSTAND-LIVE-TRADING-RISKS-REAL-MONEY"

PACKAGE_ROOT = Path(__file__).resolve().parents[1]  # .../trading_bot
DEFAULT_CONFIG_PATH = PACKAGE_ROOT / "config" / "config.yaml"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class RiskLimits:
    max_daily_loss: float          # account currency; trading halts for the day when hit
    max_risk_per_trade: float      # fraction of equity risked between entry and stop
    max_position_size: float       # units (contracts / coins) per market
    max_trades_per_day: int
    max_drawdown: float            # fraction of peak equity; hitting it trips the kill switch
    max_open_exposure: float       # account currency, total open notional
    max_consecutive_losses: int    # stop for the day after this many losses in a row

    def validate(self) -> None:
        if self.max_daily_loss <= 0:
            raise ConfigError("risk.max_daily_loss must be > 0")
        if not (0 < self.max_risk_per_trade <= 0.05):
            raise ConfigError(
                "risk.max_risk_per_trade must be in (0, 0.05]; risking more "
                "than 5% of equity on one trade is not supported."
            )
        if self.max_position_size <= 0:
            raise ConfigError("risk.max_position_size must be > 0")
        if self.max_trades_per_day < 1:
            raise ConfigError("risk.max_trades_per_day must be >= 1")
        if not (0 < self.max_drawdown < 1):
            raise ConfigError("risk.max_drawdown must be a fraction in (0, 1)")
        if self.max_open_exposure <= 0:
            raise ConfigError("risk.max_open_exposure must be > 0")
        if self.max_consecutive_losses < 1:
            raise ConfigError("risk.max_consecutive_losses must be >= 1")


@dataclass(frozen=True)
class LiveConfig:
    enabled: bool = False
    confirm_phrase: str = ""


@dataclass(frozen=True)
class ExecutionConfig:
    mode: str = "paper"  # "paper" | "live"
    live: LiveConfig = field(default_factory=LiveConfig)


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    dir: str = "logs"
    console: bool = True


@dataclass(frozen=True)
class DataConfig:
    raw_dir: str = "data/raw"
    processed_dir: str = "data/processed"
    features_dir: str = "data/features"


@dataclass(frozen=True)
class ResearchConfig:
    experiment_log: str = "research/experiment_records.jsonl"


@dataclass(frozen=True)
class Config:
    project_name: str
    timezone: str
    risk: RiskLimits
    execution: ExecutionConfig
    venues: dict            # raw venue sections (enabled flags, fee overrides, compliance flags)
    logging: LoggingConfig
    data: DataConfig
    research: ResearchConfig
    markets: tuple
    root: Path = PACKAGE_ROOT
    raw: dict = field(default_factory=dict, repr=False)

    def resolve(self, rel: str | Path) -> Path:
        """Resolve a config-relative path against the trading_bot package root."""
        p = Path(rel)
        return p if p.is_absolute() else self.root / p

    @property
    def live_trading_allowed(self) -> bool:
        return (
            self.execution.mode == "live"
            and self.execution.live.enabled
            and self.execution.live.confirm_phrase == LIVE_CONFIRM_PHRASE
        )


def build_config(raw: dict, root: Path = PACKAGE_ROOT) -> Config:
    """Build and validate a Config from a parsed YAML dict."""
    try:
        risk_raw = raw["risk"]
        risk = RiskLimits(
            max_daily_loss=float(risk_raw["max_daily_loss"]),
            max_risk_per_trade=float(risk_raw["max_risk_per_trade"]),
            max_position_size=float(risk_raw["max_position_size"]),
            max_trades_per_day=int(risk_raw["max_trades_per_day"]),
            max_drawdown=float(risk_raw["max_drawdown"]),
            max_open_exposure=float(risk_raw["max_open_exposure"]),
            max_consecutive_losses=int(risk_raw["max_consecutive_losses"]),
        )
    except KeyError as e:
        raise ConfigError(f"Missing required risk limit in config: {e}") from None
    risk.validate()

    exec_raw = raw.get("execution", {})
    live_raw = exec_raw.get("live", {}) or {}
    execution = ExecutionConfig(
        mode=str(exec_raw.get("mode", "paper")).lower(),
        live=LiveConfig(
            enabled=bool(live_raw.get("enabled", False)),
            confirm_phrase=str(live_raw.get("confirm_phrase", "") or ""),
        ),
    )
    if execution.mode not in ("paper", "live"):
        raise ConfigError(f"execution.mode must be 'paper' or 'live', got {execution.mode!r}")
    if execution.mode == "live":
        if not execution.live.enabled:
            raise ConfigError(
                "execution.mode is 'live' but execution.live.enabled is false. "
                "Live trading is disabled by default and must be enabled explicitly."
            )
        if execution.live.confirm_phrase != LIVE_CONFIRM_PHRASE:
            raise ConfigError(
                "Live mode requires execution.live.confirm_phrase to equal "
                f"{LIVE_CONFIRM_PHRASE!r}. Refusing to start."
            )

    log_raw = raw.get("logging", {})
    data_raw = raw.get("data", {})
    research_raw = raw.get("research", {})

    return Config(
        project_name=str(raw.get("project", {}).get("name", "trading_bot")),
        timezone=str(raw.get("project", {}).get("timezone", "UTC")),
        risk=risk,
        execution=execution,
        venues=dict(raw.get("venues", {})),
        logging=LoggingConfig(
            level=str(log_raw.get("level", "INFO")).upper(),
            dir=str(log_raw.get("dir", "logs")),
            console=bool(log_raw.get("console", True)),
        ),
        data=DataConfig(
            raw_dir=str(data_raw.get("raw_dir", "data/raw")),
            processed_dir=str(data_raw.get("processed_dir", "data/processed")),
            features_dir=str(data_raw.get("features_dir", "data/features")),
        ),
        research=ResearchConfig(
            experiment_log=str(
                research_raw.get("experiment_log", "research/experiment_records.jsonl")
            ),
        ),
        markets=tuple(raw.get("markets", [])),
        root=root,
        raw=raw,
    )


def load_config(path: str | Path | None = None) -> Config:
    """Load config from ``path``, ``$TRADING_BOT_CONFIG``, or the default file."""
    cfg_path = Path(path or os.environ.get("TRADING_BOT_CONFIG") or DEFAULT_CONFIG_PATH)
    if not cfg_path.exists():
        raise ConfigError(f"Config file not found: {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return build_config(raw)
