"""Phase 11 ML machinery: dataset alignment (leak geometry), the model
ladder, and the accept/reject honesty of the baseline-vs-filter comparison.

The two experiments that matter:
* planted edge  -> the machinery must FIND it (verdict CANDIDATE);
* pure noise    -> the machinery must SAY SO (verdict REJECT).
A pipeline that can't do both is worse than no ML at all.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from trading_bot.backtesting.engine import Trade
from trading_bot.core.types import Side
from trading_bot.models.dataset import build_trade_dataset
from trading_bot.models.ml_model import MODEL_LADDER, SetupFilter
from trading_bot.research.ml_experiment import (
    format_ml_comparison,
    run_ml_filter_experiment,
)

IDX = pd.date_range("2025-01-01", periods=400, freq="1h", tz="UTC")


def mk_trade(entry_ts, net_pnl, direction=Side.LONG) -> Trade:
    return Trade(
        market_id="SYNTH", direction=direction,
        entry_ts=entry_ts.to_pydatetime(), entry_price=100.0,
        exit_ts=(entry_ts + timedelta(hours=1)).to_pydatetime(), exit_price=101.0,
        size=1.0, stop_price=95.0, tp_price=None,
        entry_reason="test", exit_reason="signal_flip",
        gross_pnl=net_pnl, fees=0.0, funding=0.0, slippage_cost=0.0,
        net_pnl=net_pnl, bars_held=1,
    )


# ---- dataset alignment ----------------------------------------------------------
def test_dataset_uses_signal_bar_features():
    features = pd.DataFrame({"f": np.arange(10, dtype=float)}, index=IDX[:10])
    trades = [mk_trade(IDX[5], 50.0)]  # entered during bar 5 -> signal bar is 4
    ds = build_trade_dataset(trades, features)
    assert len(ds) == 1
    assert ds.X["f"].iloc[0] == 4.0
    assert bool(ds.y.iloc[0]) is True
    assert ds.pnls.iloc[0] == 50.0


def test_dataset_skips_unalignable_trades():
    features = pd.DataFrame({"f": np.arange(10, dtype=float)}, index=IDX[:10])
    trades = [
        mk_trade(IDX[0], 10.0),                                   # no prior bar
        mk_trade(IDX[5] + timedelta(minutes=7), 10.0),            # not on the grid
        mk_trade(IDX[6], -10.0),                                  # fine
    ]
    ds = build_trade_dataset(trades, features)
    assert len(ds) == 1
    assert ds.n_skipped == 2


def test_dataset_rejects_when_nothing_aligns():
    features = pd.DataFrame({"f": [1.0]}, index=IDX[:1])
    with pytest.raises(ValueError, match="aligned"):
        build_trade_dataset([mk_trade(IDX[300], 1.0)], features)


# ---- model ladder ---------------------------------------------------------------
def _separable(n=400, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(n, 3)), columns=["a", "b", "c"])
    y = pd.Series(X["a"].to_numpy() > 0)
    return X, y


@pytest.mark.parametrize("model", MODEL_LADDER)
def test_ladder_models_learn_separable_data(model):
    X, y = _separable()
    filt = SetupFilter(model=model, threshold=0.5).fit(X.iloc[:300], y.iloc[:300])
    acc = (filt.decide(X.iloc[300:]) == y.iloc[300:].to_numpy()).mean()
    assert acc > 0.85, f"{model} failed on trivially separable data"


def test_filter_guards():
    X, y = _separable(100)
    with pytest.raises(ValueError, match="threshold"):
        SetupFilter(threshold=1.5)
    with pytest.raises(ValueError, match="unknown model"):
        SetupFilter(model="deep_net_9000")
    with pytest.raises(RuntimeError, match="before fit"):
        SetupFilter().predict_proba(X)
    with pytest.raises(ValueError, match="single-class"):
        SetupFilter().fit(X, pd.Series([True] * len(X)))
    filt = SetupFilter().fit(X, y)
    with pytest.raises(ValueError, match="columns"):
        filt.predict_proba(X.rename(columns={"a": "z"}))


# ---- experiment honesty ---------------------------------------------------------
def _experiment_inputs(edge: bool, n=360, seed=11):
    """Trades whose outcome is either driven by a feature (edge) or pure
    noise with negative drift (no edge)."""
    rng = np.random.default_rng(seed)
    alpha = rng.normal(size=n)
    features = pd.DataFrame(
        {"alpha": alpha, "junk1": rng.normal(size=n), "junk2": rng.normal(size=n)},
        index=IDX[:n],
    )
    trades = []
    for i in range(n - 1):
        if edge:
            base = 100.0 if alpha[i] > 0 else -80.0
            pnl = base + rng.normal(0, 30)
        else:
            pnl = rng.normal(-5, 60)  # negative-expectancy noise
        trades.append(mk_trade(IDX[i + 1], float(pnl)))
    return trades, features


def test_planted_edge_is_found():
    trades, features = _experiment_inputs(edge=True)
    c = run_ml_filter_experiment(
        trades=trades, features=features, split_ts=IDX[240], model="logistic",
    )
    assert c.accepted, c.verdict
    assert c.filtered_test["expectancy"] > c.baseline_test["expectancy"]
    assert c.filtered_test["expectancy"] > 0
    # The informative feature should dominate the importances.
    assert max(c.feature_importances, key=c.feature_importances.get) == "alpha"


def test_pure_noise_is_rejected():
    trades, features = _experiment_inputs(edge=False)
    c = run_ml_filter_experiment(
        trades=trades, features=features, split_ts=IDX[240], model="logistic",
    )
    assert not c.accepted
    assert c.verdict.startswith("REJECT")


def test_insufficient_data_is_named_not_papered_over():
    trades, features = _experiment_inputs(edge=True, n=40)
    c = run_ml_filter_experiment(
        trades=trades, features=features, split_ts=IDX[20],
    )
    assert c.verdict.startswith("INSUFFICIENT DATA")


def test_experiment_is_logged(tmp_path):
    from trading_bot.research.experiment_log import ExperimentLog

    log = ExperimentLog(tmp_path / "exp.jsonl")
    trades, features = _experiment_inputs(edge=True)
    run_ml_filter_experiment(
        trades=trades, features=features, split_ts=IDX[240],
        experiment_log=log, dataset_desc="SYNTH@1h test",
    )
    records = log.load_all()
    assert len(records) == 1
    assert records[0]["strategy"] == "ml_filter:logistic"
    assert "verdict" in records[0]["results"]


def test_report_renders():
    trades, features = _experiment_inputs(edge=True)
    c = run_ml_filter_experiment(trades=trades, features=features, split_ts=IDX[240])
    text = format_ml_comparison(c)
    assert "BASELINE vs ML FILTER" in text
    assert "VERDICT" in text
