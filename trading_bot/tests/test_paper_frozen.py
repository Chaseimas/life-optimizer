"""Frozen candidate in the paper trader: immutable configuration, full event
logging, PAPER stamping, override refusal."""

from __future__ import annotations

import json

import pytest

from trading_bot import paper_trade

CANDIDATE = "orb_eth_15m_maker_p2"


def test_frozen_replay_session_produces_full_audit_trail(tmp_path):
    run_dir = tmp_path / "run"
    rc = paper_trade.main([
        "--frozen", CANDIDATE, "--replay",
        "--max-bars", "600", "--run-dir", str(run_dir),
    ])
    assert rc == 0

    # The frozen definition travels with the session, stamped PAPER:
    frozen_file = json.loads((run_dir / "frozen_candidate.json").read_text())
    assert frozen_file["candidate"] == CANDIDATE
    assert frozen_file["mode"] == "PAPER"
    assert frozen_file["definition"]["params"]["range_minutes"] == 60

    result = json.loads((run_dir / "result.json").read_text())
    assert result["mode"] == "PAPER"
    state = json.loads((run_dir / "state.json").read_text())
    assert state["mode"] == "PAPER"
    assert state["maker_stats"] is not None       # maker execution was active

    events = [json.loads(l) for l in (run_dir / "events.jsonl").read_text().splitlines() if l]
    assert events, "event log must not be empty"
    kinds = {e["event"] for e in events}
    assert "order_placed" in kinds                # simulated orders were logged
    assert all(e["mode"] == "PAPER" for e in events)
    # Every event carries bar time and wall time -> reconstructable timeline.
    assert all("bar_ts" in e and "wall_ts" in e for e in events)
    # Placements must match the engine's own accounting:
    placed_events = sum(1 for e in events if e["event"] == "order_placed")
    assert placed_events == state["maker_stats"]["orders_placed"]


def test_frozen_refuses_parameter_overrides(tmp_path):
    rc = paper_trade.main([
        "--frozen", CANDIDATE, "--replay",
        "--strategy", "rolling_vwap",             # attempted drift
        "--run-dir", str(tmp_path / "x"),
    ])
    assert rc == 1
    assert not (tmp_path / "x").exists()          # session never started


def test_unknown_frozen_candidate_rejected(tmp_path):
    with pytest.raises(KeyError, match="Unknown frozen candidate"):
        paper_trade.main([
            "--frozen", "holy_grail_v2", "--replay",
            "--run-dir", str(tmp_path / "y"),
        ])
