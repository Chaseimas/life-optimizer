"""Baseline-vs-ML comparison (Phase 11).

Protocol:
1. Take a baseline strategy's realized trades and the leak-tested feature
   matrix; build the trade dataset (features at the signal bar).
2. Split BY TIME at ``split_ts``: earlier trades train the filter, later
   trades are the held-out test. Never shuffled.
3. Fit the filter on train; on test, keep only trades the filter approves.
4. Compare filtered vs unfiltered TEST trades. The ML filter is accepted
   only if it clears every acceptance criterion; otherwise REJECT, stated
   plainly. "Sounds more sophisticated" is not a criterion.

Caveat (stated, not hidden): filtering is evaluated trade-by-trade on the
baseline's realized trades; equity compounding of skipped trades is not
re-simulated. Fine for accept/reject research; a full re-simulation follows
only for filters that pass here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from trading_bot.backtesting.engine import Trade
from trading_bot.backtesting.metrics import trade_stats
from trading_bot.models.dataset import TradeDataset, build_trade_dataset
from trading_bot.models.ml_model import SetupFilter
from trading_bot.monitoring.logging import get_logger

log = get_logger("ml_experiment")

MIN_TRAIN_TRADES = 50
MIN_TEST_TRADES = 30


@dataclass
class MLFilterComparison:
    model: str
    threshold: float
    split_ts: pd.Timestamp
    n_train: int
    n_test: int
    n_kept: int
    kept_fraction: float | None
    baseline_test: dict          # trade_stats of ALL test trades
    filtered_test: dict          # trade_stats of filter-approved test trades
    verdict: str                 # starts with "REJECT", "CANDIDATE", or "INSUFFICIENT DATA"
    feature_importances: dict = field(default_factory=dict)
    notes: str = ""

    @property
    def accepted(self) -> bool:
        return self.verdict.startswith("CANDIDATE")


def _verdict(baseline: dict, filtered: dict, kept_fraction: float,
             min_kept_fraction: float) -> str:
    if kept_fraction < min_kept_fraction:
        return (
            f"REJECT: filter keeps only {kept_fraction:.0%} of test trades "
            f"(minimum {min_kept_fraction:.0%}) — too selective to trust or trade"
        )
    if filtered["n_trades"] < MIN_TEST_TRADES:
        return f"REJECT: only {filtered['n_trades']} approved test trades — not evaluable"
    base_exp = baseline["expectancy"]
    filt_exp = filtered["expectancy"]
    if filt_exp is None or filt_exp <= 0:
        return (
            f"REJECT: filtered expectancy {filt_exp} is not positive out-of-sample "
            "— the filter does not turn this baseline into an edge"
        )
    if base_exp is not None and filt_exp <= base_exp:
        return (
            f"REJECT: filtered expectancy {filt_exp:.2f} does not beat the "
            f"unfiltered baseline {base_exp:.2f} out-of-sample"
        )
    improvement = filt_exp - (base_exp or 0.0)
    return (
        f"CANDIDATE: filtered expectancy {filt_exp:.2f}/trade vs baseline "
        f"{(base_exp or 0.0):.2f} (+{improvement:.2f}) on {filtered['n_trades']} "
        "held-out trades. Next gates before any trust: parameter/threshold "
        "sensitivity, walk-forward re-simulation, fresh out-of-sample period."
    )


def run_ml_filter_experiment(
    *,
    trades: list[Trade],
    features: pd.DataFrame,
    split_ts: pd.Timestamp,
    model: str = "logistic",
    threshold: float = 0.55,
    min_kept_fraction: float = 0.25,
    random_state: int = 42,
    experiment_log=None,
    dataset_desc: str = "",
    notes: str = "",
) -> MLFilterComparison:
    ds: TradeDataset = build_trade_dataset(trades, features)

    train_mask = ds.entry_ts < split_ts
    test_mask = ~train_mask
    n_train, n_test = int(train_mask.sum()), int(test_mask.sum())

    def _log(comparison: MLFilterComparison) -> MLFilterComparison:
        if experiment_log is not None:
            experiment_log.log(
                strategy=f"ml_filter:{model}",
                market=dataset_desc.split("@")[0] if dataset_desc else "unknown",
                params={"model": model, "threshold": threshold,
                        "split_ts": str(split_ts), "min_kept_fraction": min_kept_fraction},
                dataset=dataset_desc or "unspecified",
                train_period=f"< {split_ts}",
                test_period=f">= {split_ts}",
                results={
                    "verdict": comparison.verdict,
                    "n_train": comparison.n_train, "n_test": comparison.n_test,
                    "n_kept": comparison.n_kept,
                    "baseline_test": comparison.baseline_test,
                    "filtered_test": comparison.filtered_test,
                },
                notes=notes or "baseline-vs-ML filter comparison",
            )
        return comparison

    if n_train < MIN_TRAIN_TRADES or n_test < MIN_TEST_TRADES:
        return _log(MLFilterComparison(
            model=model, threshold=threshold, split_ts=split_ts,
            n_train=n_train, n_test=n_test, n_kept=0, kept_fraction=None,
            baseline_test=trade_stats(list(ds.pnls[test_mask])),
            filtered_test=trade_stats([]),
            verdict=(
                f"INSUFFICIENT DATA: {n_train} train / {n_test} test trades "
                f"(need >= {MIN_TRAIN_TRADES}/{MIN_TEST_TRADES}). Get more data "
                "instead of lowering the bar."
            ),
            notes=notes,
        ))

    filt = SetupFilter(model=model, threshold=threshold, random_state=random_state)
    filt.fit(ds.X[train_mask], ds.y[train_mask])

    keep = filt.decide(ds.X[test_mask])
    test_pnls = ds.pnls[test_mask]
    kept_pnls = list(test_pnls[keep])
    baseline = trade_stats(list(test_pnls))
    filtered = trade_stats(kept_pnls)
    kept_fraction = len(kept_pnls) / n_test

    importances = filt.feature_importances()
    comparison = MLFilterComparison(
        model=model, threshold=threshold, split_ts=split_ts,
        n_train=n_train, n_test=n_test, n_kept=len(kept_pnls),
        kept_fraction=kept_fraction,
        baseline_test=baseline, filtered_test=filtered,
        verdict=_verdict(baseline, filtered, kept_fraction, min_kept_fraction),
        feature_importances=(
            {k: float(v) for k, v in importances.head(10).items()}
            if importances is not None else {}
        ),
        notes=notes,
    )
    log.info("ML filter experiment: %s", comparison.verdict)
    return _log(comparison)


def format_ml_comparison(c: MLFilterComparison) -> str:
    b, f = c.baseline_test, c.filtered_test
    lines = [
        "=" * 72,
        f"BASELINE vs ML FILTER  (model={c.model}, threshold={c.threshold})",
        f"time split at {c.split_ts}: {c.n_train} train trades, {c.n_test} held-out test trades",
        "-" * 72,
        f"{'':24s}{'baseline (all test)':>22s}{'ML-filtered':>18s}",
        f"{'trades':24s}{b['n_trades']:>22d}{f['n_trades']:>18d}",
        f"{'net profit':24s}{b['net_profit']:>22,.2f}{f['net_profit']:>18,.2f}",
        f"{'expectancy/trade':24s}"
        f"{(b['expectancy'] if b['expectancy'] is not None else float('nan')):>22,.2f}"
        f"{(f['expectancy'] if f['expectancy'] is not None else float('nan')):>18,.2f}",
        f"{'win rate':24s}"
        f"{(b['win_rate'] if b['win_rate'] is not None else float('nan')):>21.1%} "
        f"{(f['win_rate'] if f['win_rate'] is not None else float('nan')):>17.1%}",
        "-" * 72,
        f"VERDICT: {c.verdict}",
    ]
    if c.feature_importances:
        top = ", ".join(f"{k}={v:.3f}" for k, v in list(c.feature_importances.items())[:5])
        lines.append(f"top features: {top}")
    lines.append("=" * 72)
    return "\n".join(lines)
