"""Frozen candidate: tamper evidence, completeness, and constructors.

The expected hashes are pinned HERE as well as in frozen_hashes.json —
changing the frozen definition requires editing the definition, the JSON,
and this test, all visible in one git diff. That friction is the feature.
"""

from __future__ import annotations

import pandas as pd
import pytest

from trading_bot.backtesting.maker import MakerParams
from trading_bot.research import frozen
from trading_bot.strategies.registry import make_strategy

CANDIDATE = "orb_eth_15m_maker_p2"

# Pinned at freeze time (2026-08-27). Do not update casually: a hash change
# here means the frozen candidate is no longer the thing Pass 2 evaluated.
EXPECTED_DEFINITION_HASH = (
    "1798a7b1d3482d944c2c37f34fb4e1d8a9cd130cf09440494d3b4a208a8b93bf"
)
EXPECTED_SOURCE_HASHES = {
    "strategies/breakout.py":
        "3d71d19d1c325f8fa4b56d2fd135b8535ab0b4d7469f14d1699c0c1bc4cd39b5",
    "backtesting/maker.py":
        "81b857f3f61024a783ff92b908403d3182c625b17ee8fca3cdfa7ca350166a7f",
}


def test_definition_hash_is_pinned():
    assert frozen.definition_hash(CANDIDATE) == EXPECTED_DEFINITION_HASH


def test_hashes_json_matches_pinned_values():
    expected = frozen.expected_hashes()
    assert expected["candidates"][CANDIDATE] == EXPECTED_DEFINITION_HASH
    assert expected["source_files"] == EXPECTED_SOURCE_HASHES


def test_pinned_source_files_unchanged():
    for rel, want in EXPECTED_SOURCE_HASHES.items():
        assert frozen.source_file_hash(rel) == want, (
            f"{rel} changed since the freeze — frozen evaluations are void "
            "until the freeze is explicitly renewed (and documented)"
        )


def test_params_are_complete_no_silent_defaults():
    frozen_def = frozen.get_frozen(CANDIDATE)
    strategy = make_strategy(frozen_def["strategy"])
    assert set(frozen_def["params"]) == set(strategy.default_params()), (
        "frozen params must spell out EVERY parameter so a changed default "
        "cannot silently alter the frozen candidate"
    )


def test_oos_boundary_after_data_used():
    frozen_def = frozen.get_frozen(CANDIDATE)
    assert (pd.Timestamp(frozen_def["oos_start"])
            > pd.Timestamp(frozen_def["data_used_through"]))
    assert (pd.Timestamp(frozen_def["planned_evaluation_date"], tz="UTC")
            > pd.Timestamp(frozen_def["oos_start"]))


def test_constructors_build_frozen_objects():
    limits = frozen.frozen_risk_limits(CANDIDATE)
    assert limits.max_daily_loss == 1500.0
    assert limits.max_risk_per_trade == 0.005

    cons = frozen.frozen_maker(CANDIDATE, "conservative")
    assert isinstance(cons, MakerParams)
    assert cons.fill_on == "through" and cons.adverse_selection_bps == 0.5
    base = frozen.frozen_maker(CANDIDATE, "baseline")
    assert base.fill_on == "prob" and base.touch_fill_prob == 0.5

    cfg = frozen.frozen_backtest_config(CANDIDATE, "baseline")
    assert cfg.maker is base or cfg.maker == base
    assert cfg.stop_atr_mult == 2.0
    assert cfg.label == f"frozen:{CANDIDATE}:baseline"


def test_unknown_names_rejected():
    with pytest.raises(KeyError, match="Unknown frozen candidate"):
        frozen.get_frozen("holy_grail_v2")
    with pytest.raises(KeyError, match="scenario"):
        frozen.frozen_maker(CANDIDATE, "optimistic")  # deliberately NOT frozen


def test_candidate_is_labeled_unvalidated():
    frozen_def = frozen.get_frozen(CANDIDATE)
    assert "NOT validated" in frozen_def["status"]
    assert "NOT authorized" in frozen_def["notes"]
