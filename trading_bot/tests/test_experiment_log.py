"""Experiment tracking: append-only, complete records, honest smoke runner."""

from __future__ import annotations

import json

import pytest

from trading_bot.research.experiment_log import ExperimentLog
from trading_bot.research.experiments import generate_synthetic_bars, run_signal_smoke_experiment
from trading_bot.strategies.momentum import SimpleMomentum


@pytest.fixture()
def exp_log(tmp_path):
    return ExperimentLog(tmp_path / "experiments.jsonl")


def test_log_and_reload(exp_log):
    rec = exp_log.log(
        strategy="simple_momentum",
        market="SYNTH",
        params={"lookback": 20},
        dataset="synthetic(seed=1)",
        results={"n_signals": 10},
        notes="unit test",
    )
    assert rec.experiment_id.startswith("exp_")
    loaded = exp_log.load_all()
    assert len(loaded) == 1
    assert loaded[0]["experiment_id"] == rec.experiment_id
    assert loaded[0]["params"] == {"lookback": 20}
    assert loaded[0]["strategy"] == "simple_momentum"


def test_append_only_and_unique_ids(exp_log):
    ids = set()
    for i in range(5):
        rec = exp_log.log(
            strategy="s", market="m", params={"i": i}, dataset="d", results={},
        )
        ids.add(rec.experiment_id)
    assert len(ids) == 5  # no collisions
    assert exp_log.count() == 5
    assert exp_log.count(strategy="s") == 5
    assert exp_log.count(strategy="other") == 0
    # File is plain JSONL: 5 lines, each independently parseable.
    lines = exp_log.path.read_text().strip().splitlines()
    assert len(lines) == 5
    for line in lines:
        json.loads(line)


def test_load_all_on_missing_file(tmp_path):
    assert ExperimentLog(tmp_path / "nope.jsonl").load_all() == []


def test_smoke_experiment_runs_and_logs(exp_log):
    bars = generate_synthetic_bars(n=300, seed=11)
    results = run_signal_smoke_experiment(
        SimpleMomentum({"lookback": 10}),
        bars,
        exp_log,
        dataset="synthetic(seed=11)",
        notes="unit test",
    )
    assert results["n_bars"] == 300
    assert results["n_signals"] > 0
    assert results["n_evaluated"] <= results["n_signals"]
    assert 0.0 <= results["hit_rate"] <= 1.0
    # The runner labels itself honestly.
    assert "Not a backtest" in results["evaluation"]
    assert exp_log.count() == 1


def test_smoke_experiment_on_random_data_shows_no_edge(exp_log):
    """On a random walk the measured hit rate must hover near 50%. If this
    fails, the evaluation itself is leaking information."""
    bars = generate_synthetic_bars(n=5000, seed=123)
    results = run_signal_smoke_experiment(
        SimpleMomentum({"lookback": 20}), bars, exp_log, dataset="synthetic(seed=123)",
    )
    assert abs(results["hit_rate"] - 0.5) < 0.05
