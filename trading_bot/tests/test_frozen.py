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

# Pinned at freeze time. Do not update casually: a hash change here means a
# frozen candidate is no longer the thing its research pass evaluated.
# (Appending NEW candidates is allowed; changing existing hashes is not.)
EXPECTED_DEFINITION_HASHES = {
    "orb_eth_15m_maker_p2":
        "1798a7b1d3482d944c2c37f34fb4e1d8a9cd130cf09440494d3b4a208a8b93bf",
    "funding_carry_btc_1h_p4":
        "8301f4f09600cc59fca4dec94d9206954cbaea83bfb507f17cbeec992f4a2161",
}
EXPECTED_DEFINITION_HASH = EXPECTED_DEFINITION_HASHES[CANDIDATE]
EXPECTED_SOURCE_HASHES = {
    "strategies/breakout.py":
        "3d71d19d1c325f8fa4b56d2fd135b8535ab0b4d7469f14d1699c0c1bc4cd39b5",
    "strategies/funding_carry.py":
        "4744fc30f223769cc51c003d63a3e56e585d1100ee87f4efed65d14278edb3e6",
    "backtesting/maker.py":
        "81b857f3f61024a783ff92b908403d3182c625b17ee8fca3cdfa7ca350166a7f",
}


def test_definition_hashes_are_pinned():
    for name, want in EXPECTED_DEFINITION_HASHES.items():
        assert frozen.definition_hash(name) == want, name


def test_hashes_json_matches_pinned_values():
    expected = frozen.expected_hashes()
    assert expected["candidates"] == EXPECTED_DEFINITION_HASHES
    assert expected["source_files"] == EXPECTED_SOURCE_HASHES


def test_pinned_source_files_unchanged():
    for rel, want in EXPECTED_SOURCE_HASHES.items():
        assert frozen.source_file_hash(rel) == want, (
            f"{rel} changed since the freeze — frozen evaluations are void "
            "until the freeze is explicitly renewed (and documented)"
        )


def test_params_are_complete_no_silent_defaults():
    from trading_bot.strategies.funding_carry import FundingCarry
    from trading_bot.strategies.registry import STRATEGY_REGISTRY

    extra = {"funding_carry": FundingCarry}
    for name, frozen_def in frozen.FROZEN_CANDIDATES.items():
        cls = STRATEGY_REGISTRY.get(frozen_def["strategy"]) or extra[frozen_def["strategy"]]
        assert set(frozen_def["params"]) == set(cls.default_params()), (
            f"{name}: frozen params must spell out EVERY parameter so a "
            "changed default cannot silently alter the frozen candidate"
        )


def test_oos_boundary_after_data_used():
    for frozen_def in frozen.FROZEN_CANDIDATES.values():
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


def test_every_candidate_is_labeled_unvalidated():
    for frozen_def in frozen.FROZEN_CANDIDATES.values():
        assert "NOT validated" in frozen_def["status"]
        assert "NOT authorized" in frozen_def["notes"]


def test_funding_candidate_constructors():
    limits = frozen.frozen_risk_limits("funding_carry_btc_1h_p4")
    assert limits.max_risk_per_trade == 0.005
    cfg = frozen.frozen_backtest_config("funding_carry_btc_1h_p4", "conservative")
    assert cfg.maker.fill_on == "through"
    crit = frozen.get_frozen("funding_carry_btc_1h_p4")["evaluation_criteria"]
    assert crit["beta_control_mode"] == "mixed_and_sides"
