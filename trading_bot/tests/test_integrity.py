"""Research-integrity checks: tamper detection, OOS-tuning detection,
cost transparency, paper labeling — and a live audit of the actual repo."""

from __future__ import annotations

import json

import pytest

from trading_bot.core.config import load_config
from trading_bot.research import frozen as frozen_mod
from trading_bot.research.integrity import (
    audit_experiment_log,
    audit_paper_runs,
    check_frozen_hashes,
    run_all,
)

CANDIDATE = "orb_eth_15m_maker_p2"


def violations(findings):
    return [f for f in findings if f.severity == "VIOLATION"]


def test_frozen_hashes_clean():
    assert violations(check_frozen_hashes()) == []


def test_tampered_definition_is_detected(monkeypatch):
    monkeypatch.setitem(
        frozen_mod.FROZEN_CANDIDATES[CANDIDATE]["params"], "range_minutes", 90
    )
    found = violations(check_frozen_hashes())
    assert found and "CHANGED" in found[0].detail


def _write_log(tmp_path, records):
    path = tmp_path / "log.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return path


def _rec(i, **over):
    base = {
        "experiment_id": f"exp_{i}",
        "created_at": "2026-08-20T00:00:00+00:00",
        "strategy": "opening_range_breakout",
        "market": "HL:ETH",
        "dataset": "HL:ETH@15m hyperliquid_api",
        "params": {"range_minutes": 60, "buffer_frac": 0.0,
                   "range_start_hour": 0, "flat_hour": 23},
        "results": {"execution_model": "maker_entry_taker_exit", "fees": 1.0},
        "notes": "",
    }
    base.update(over)
    return base


def test_audit_flags_post_freeze_tuning(tmp_path):
    path = _write_log(tmp_path, [
        _rec(1),                                                    # pre-freeze: fine
        _rec(2, created_at="2026-09-05T00:00:00+00:00",
             params={"range_minutes": 90, "buffer_frac": 0.0}),     # OOS tuning!
        _rec(3, created_at="2026-09-05T00:00:00+00:00",
             params={"range_minutes": 120, "buffer_frac": 0.1},
             notes="exploratory: labeled variant, kept separate"),  # allowed
    ])
    found = violations(audit_experiment_log(path))
    assert len(found) == 1
    assert found[0].check == "oos_tuning"
    assert "exp_2" in found[0].detail
    assert "exp_3" not in found[0].detail


def test_audit_flags_duplicate_ids(tmp_path):
    path = _write_log(tmp_path, [_rec(1), _rec(1)])
    assert any(f.check == "experiment_log" for f in violations(audit_experiment_log(path)))


def test_audit_flags_costless_pass3_records(tmp_path):
    path = _write_log(tmp_path, [
        _rec(1, notes="pass3 something", results={"net": 5.0}),     # no cost info
    ])
    found = violations(audit_experiment_log(path))
    assert any(f.check == "cost_transparency" for f in found)


def test_audit_reports_selection_bias_denominator(tmp_path):
    path = _write_log(tmp_path, [_rec(1), _rec(2, strategy="simple_momentum")])
    findings = audit_experiment_log(path)
    denom = [f for f in findings if f.check == "selection_bias"]
    assert denom and "opening_range_breakout" in denom[0].detail


def test_paper_runs_labeling(tmp_path):
    good = tmp_path / "runs" / "good"
    good.mkdir(parents=True)
    (good / "result.json").write_text(json.dumps({"mode": "PAPER"}))
    assert violations(audit_paper_runs(tmp_path / "runs")) == []

    bad = tmp_path / "runs" / "bad"
    bad.mkdir()
    (bad / "result.json").write_text(json.dumps({"mode": "LIVE"}))
    found = violations(audit_paper_runs(tmp_path / "runs"))
    assert found and "PAPER" in found[0].detail


def test_live_audit_of_this_repository_is_clean():
    """The real repo must pass its own integrity checks at all times."""
    findings, ok = run_all(load_config())
    assert ok, [f for f in findings if f.severity == "VIOLATION"]
