"""Frozen evaluation: strict OOS slicing, both scenarios, pre-registered
criteria, and honest behavior when no OOS data exists yet."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from trading_bot.data_pipeline.frames import bars_to_frame
from trading_bot.data_pipeline.store import BarStore
from trading_bot.research.experiments import generate_synthetic_bars
from trading_bot.research.frozen import get_frozen
from trading_bot.research.frozen_eval import evaluate

CANDIDATE = "orb_eth_15m_maker_p2"


@pytest.fixture()
def synthetic_store(tmp_path):
    """A store whose HL:ETH 15m data spans ACROSS the frozen OOS boundary —
    synthetic bars, used purely to exercise the evaluation machinery."""
    store = BarStore(tmp_path / "raw", tmp_path / "processed")
    bars = generate_synthetic_bars(
        n=2500, seed=99, market_id="HL:ETH",
        start=datetime(2026, 8, 25, tzinfo=timezone.utc),
        freq_minutes=15, s0=4300.0,
    )
    store.save(bars_to_frame(bars), market_id="HL:ETH", interval="15m",
               stage="processed", source="synthetic-eval-test")
    return store


def test_no_oos_data_yet_on_real_store():
    """The committed real dataset ends before oos_start — the evaluator must
    say so instead of inventing a result."""
    out = evaluate(CANDIDATE, skip_control=True, log_experiment=False)
    assert out["oos_bars"] == 0
    assert out["verdict"].startswith("NO OOS DATA YET")


def test_evaluation_runs_both_scenarios_strictly_oos(synthetic_store):
    out = evaluate(CANDIDATE, skip_control=True, log_experiment=False,
                   store=synthetic_store)
    frozen = get_frozen(CANDIDATE)
    assert out["oos_bars"] > 0
    assert set(out["scenarios"]) == set(frozen["maker_scenarios"])
    for entry in out["scenarios"].values():
        for key in ("net", "trades", "fill_rate", "fees", "long_net", "short_net"):
            assert key in entry
    # The engine-level assert inside evaluate() already guarantees no trade
    # entered before oos_start; reaching here means it held.
    assert "criteria_checks" in out
    assert "min_oos_trades" in out["criteria_checks"]
    assert isinstance(out["verdict"], str) and out["verdict"]
    assert out["early_peek"] is True          # today < planned evaluation date
    assert len(out["definition_sha256"]) == 64


def test_as_of_limits_the_window(synthetic_store):
    full = evaluate(CANDIDATE, skip_control=True, log_experiment=False,
                    store=synthetic_store)
    short = evaluate(CANDIDATE, skip_control=True, log_experiment=False,
                     store=synthetic_store, as_of="2026-09-01")
    assert short["oos_bars"] < full["oos_bars"]
    assert pd.Timestamp(short["oos_end"]) <= pd.Timestamp("2026-09-01", tz="UTC")


def test_verdict_uses_preregistered_min_trades(synthetic_store):
    out = evaluate(CANDIDATE, skip_control=True, log_experiment=False,
                   store=synthetic_store, as_of="2026-08-29")
    # A ~1-day window cannot produce 30 trades: verdict must be the
    # pre-registered INSUFFICIENT branch, not an opinion.
    assert not out["criteria_checks"]["min_oos_trades"]
    assert out["verdict"].startswith("INSUFFICIENT DATA")
