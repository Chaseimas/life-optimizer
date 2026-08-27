"""Frozen research candidates (pre-registered, tamper-evident).

A frozen candidate is a COMPLETE, immutable definition of a strategy
configuration as it stood when a research pass ended: strategy, parameters,
market, execution assumptions, risk limits, the data boundary it has already
seen, the pre-registered evaluation date, and the pre-registered success
criteria. Future evaluations run THIS definition, verbatim — never a tuned
variant, never with assumptions picked after seeing new results.

Tamper evidence: ``definition_hash()`` produces a SHA-256 over the canonical
JSON of a candidate, and source-file hashes pin the strategy and fill-model
code. Expected values live in ``frozen_hashes.json`` and in the test suite;
``research/integrity.py`` verifies both. Changing any frozen value requires
editing multiple files — loudly visible in git history — which is the point:
freezing cannot be silently undone.

The Pass-2 verdict for the candidate below is INSUFFICIENT EVIDENCE. It is a
research candidate, not a validated strategy. No live trading is authorized.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from trading_bot.backtesting.engine import BacktestConfig
from trading_bot.backtesting.maker import MakerParams
from trading_bot.core.config import RiskLimits

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
HASHES_PATH = Path(__file__).resolve().parent / "frozen_hashes.json"

# Source files whose behavior the frozen candidate depends on directly.
# Editing them after the freeze voids prior frozen evaluations until the
# freeze is explicitly renewed (update hashes + say so in FINDINGS.md).
FROZEN_SOURCE_FILES = (
    "strategies/breakout.py",       # ORB candidate strategy logic
    "strategies/funding_carry.py",  # funding-carry candidate strategy logic
    "backtesting/maker.py",         # the fill model semantics
)

FROZEN_CANDIDATES: dict[str, dict] = {
    "orb_eth_15m_maker_p2": {
        "frozen_at": "2026-08-27",
        "frozen_in_pass": 2,
        "status": "INSUFFICIENT EVIDENCE — research candidate only, NOT validated",
        "strategy": "opening_range_breakout",
        # Full parameter set, defaults spelled out so silent default drift
        # cannot change behavior:
        "params": {
            "range_start_hour": 0,
            "range_minutes": 60,
            "buffer_frac": 0.0,
            "flat_hour": 23,
        },
        "market": "HL:ETH",
        "interval": "15m",
        "backtest": {
            "initial_equity": 100_000.0,
            "risk_per_trade": None,          # falls back to risk_limits value
            "fixed_stop_points": None,
            "fixed_tp_points": None,
            "stop_atr_mult": 2.0,
            "tp_atr_mult": None,
            "atr_period": 14,
            "allow_short": True,
        },
        # Both honest execution scenarios, values inlined (NOT references to
        # SCENARIOS — if that registry ever changes, this must not):
        "maker_scenarios": {
            "conservative": {
                "limit_offset_bps": 0.0, "max_lifetime_bars": 2,
                "fill_on": "through", "penetration_bps": 1.0,
                "touch_fill_prob": 0.5, "partial_fill_frac": 1.0,
                "min_fill_frac": 0.1, "adverse_selection_bps": 0.5, "seed": 7,
            },
            "baseline": {
                "limit_offset_bps": 0.0, "max_lifetime_bars": 3,
                "fill_on": "prob", "penetration_bps": 1.0,
                "touch_fill_prob": 0.5, "partial_fill_frac": 1.0,
                "min_fill_frac": 0.1, "adverse_selection_bps": 0.25, "seed": 7,
            },
        },
        # Risk limits snapshot at freeze time (config.yaml may drift; the
        # frozen evaluation must not):
        "risk_limits": {
            "max_daily_loss": 1500.0,
            "max_risk_per_trade": 0.005,
            "max_position_size": 1000,
            "max_trades_per_day": 8,
            "max_drawdown": 0.10,
            "max_open_exposure": 60000.0,
            "max_consecutive_losses": 5,
        },
        # Contamination boundary: every bar with close time <= this was
        # available during Pass 2 research and is therefore IN-SAMPLE.
        "data_used_through": "2026-08-27T19:00:00+00:00",
        # Genuinely untouched out-of-sample starts here (clean day boundary):
        "oos_start": "2026-08-28T00:00:00+00:00",
        # Pre-registered evaluation schedule (defined BEFORE seeing OOS data):
        "planned_evaluation_date": "2026-10-01",
        "fallback_evaluation_date": "2026-11-01",
        # Pre-registered success criteria — evaluated as written, no post-hoc
        # adjustment. Anything else is INSUFFICIENT EVIDENCE, continued.
        "evaluation_criteria": {
            "min_oos_trades": 30,
            "require_positive_net_in_scenarios": ["conservative", "baseline"],
            "long_only_beta_control_min_percentile": 0.95,
            "beta_control_replicates": 200,
            "beta_control_seed": 2026,
            "if_min_trades_not_met": "extend to fallback_evaluation_date",
        },
        "notes": (
            "Pass-2 verdict: INSUFFICIENT EVIDENCE (long-only beta control at "
            "93% vs 95% bar; one market; 52 days; one +43% regime; "
            "outlier-dependent; OOS bootstrap P(<=0)=34%). Live trading is "
            "NOT authorized."
        ),
    },
    "funding_carry_btc_1h_p4": {
        "frozen_at": "2026-08-27",
        "frozen_in_pass": 4,
        "status": "INSUFFICIENT EVIDENCE — research candidate only, NOT validated",
        "strategy": "funding_carry",
        "params": {
            "lookback_hours": 24,
            "rank_window_hours": 720,
            "entry_pctile": 0.9,
            "neutral_band": 0.10,
        },
        "market": "HL:BTC",
        "interval": "1h",
        "backtest": {
            "initial_equity": 100_000.0,
            "risk_per_trade": None,
            "fixed_stop_points": None,
            "fixed_tp_points": None,
            "stop_atr_mult": 2.0,
            "tp_atr_mult": None,
            "atr_period": 14,
            "allow_short": True,
        },
        "maker_scenarios": {
            "conservative": {
                "limit_offset_bps": 0.0, "max_lifetime_bars": 2,
                "fill_on": "through", "penetration_bps": 1.0,
                "touch_fill_prob": 0.5, "partial_fill_frac": 1.0,
                "min_fill_frac": 0.1, "adverse_selection_bps": 0.5, "seed": 7,
            },
            "baseline": {
                "limit_offset_bps": 0.0, "max_lifetime_bars": 3,
                "fill_on": "prob", "penetration_bps": 1.0,
                "touch_fill_prob": 0.5, "partial_fill_frac": 1.0,
                "min_fill_frac": 0.1, "adverse_selection_bps": 0.25, "seed": 7,
            },
        },
        "risk_limits": {
            "max_daily_loss": 1500.0,
            "max_risk_per_trade": 0.005,
            "max_position_size": 1000,
            "max_trades_per_day": 8,
            "max_drawdown": 0.10,
            "max_open_exposure": 60000.0,
            "max_consecutive_losses": 5,
        },
        "data_used_through": "2026-08-27T19:00:00+00:00",
        "oos_start": "2026-08-28T00:00:00+00:00",
        # ~0.25 trades/day -> a meaningful trade count needs months, and the
        # strategy also needs live funding-rate history accumulated:
        "planned_evaluation_date": "2026-11-30",
        "fallback_evaluation_date": "2027-01-31",
        "evaluation_criteria": {
            "min_oos_trades": 20,
            "require_positive_net_in_scenarios": ["conservative", "baseline"],
            # Both sides trade, so the control is mixed + per-side:
            "beta_control_mode": "mixed_and_sides",
            "mixed_beta_control_min_percentile": 0.95,
            "side_beta_control_min_percentile": 0.90,
            "beta_control_replicates": 200,
            "beta_control_seed": 2026,
            "if_min_trades_not_met": "extend to fallback_evaluation_date",
        },
        "notes": (
            "Pass-4 verdict: INSUFFICIENT EVIDENCE, strongest candidate to "
            "date. For: OOS +$5.6-6.1k across taker AND both maker scenarios "
            "(PF 1.7-1.8, Sharpe ~1.8, maxDD <4%), perfectly stable WF params, "
            "both sides profitable, made money in the -13% bear third, robust "
            "to 2x fees + 3x slippage. Against: 30 OOS trades; 1-of-3 markets "
            "(ETH/SOL failed); per-side controls 92-94% (mixed 96-98% "
            "separates); bootstrap P(<=0)=29%; one 200-day window; ~8 strategy "
            "families tested on the same data (multiple-comparisons debt). "
            "Live trading is NOT authorized."
        ),
    },
}


def canonical_json(candidate_name: str) -> str:
    return json.dumps(FROZEN_CANDIDATES[candidate_name], sort_keys=True,
                      separators=(",", ":"))


def definition_hash(candidate_name: str) -> str:
    return hashlib.sha256(canonical_json(candidate_name).encode()).hexdigest()


def source_file_hash(rel_path: str) -> str:
    return hashlib.sha256((PACKAGE_ROOT / rel_path).read_bytes()).hexdigest()


def expected_hashes() -> dict:
    return json.loads(HASHES_PATH.read_text())


# ---- constructors: the ONLY way frozen evaluations build their objects ---------
def get_frozen(candidate_name: str) -> dict:
    try:
        return FROZEN_CANDIDATES[candidate_name]
    except KeyError:
        raise KeyError(
            f"Unknown frozen candidate {candidate_name!r}. "
            f"Known: {sorted(FROZEN_CANDIDATES)}"
        ) from None


def frozen_risk_limits(candidate_name: str) -> RiskLimits:
    limits = RiskLimits(**get_frozen(candidate_name)["risk_limits"])
    limits.validate()
    return limits


def frozen_maker(candidate_name: str, scenario: str) -> MakerParams:
    scenarios = get_frozen(candidate_name)["maker_scenarios"]
    if scenario not in scenarios:
        raise KeyError(f"scenario must be one of {sorted(scenarios)}")
    params = MakerParams(**scenarios[scenario])
    params.validate()
    return params


def frozen_backtest_config(candidate_name: str, scenario: str) -> BacktestConfig:
    bt = get_frozen(candidate_name)["backtest"]
    return BacktestConfig(
        initial_equity=bt["initial_equity"],
        risk_per_trade=bt["risk_per_trade"],
        fixed_stop_points=bt["fixed_stop_points"],
        fixed_tp_points=bt["fixed_tp_points"],
        stop_atr_mult=bt["stop_atr_mult"],
        tp_atr_mult=bt["tp_atr_mult"],
        atr_period=bt["atr_period"],
        allow_short=bt["allow_short"],
        maker=frozen_maker(candidate_name, scenario),
        label=f"frozen:{candidate_name}:{scenario}",
    )
