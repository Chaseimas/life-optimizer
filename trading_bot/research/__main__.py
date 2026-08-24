"""Phase 1 research pipeline smoke experiment.

Usage (from the repo root):
    python -m trading_bot.research
    # or: python trading_bot/research.py

What it does: generates SYNTHETIC random-walk bars, runs the SimpleMomentum
baseline over them, evaluates signals against next-bar returns, and appends
the outcome to the experiment log.

What it proves: the plumbing works and is look-ahead-safe.
What it does NOT prove: any edge. The data is random by construction.
"""

from __future__ import annotations

from trading_bot.core.config import load_config
from trading_bot.monitoring.logging import get_logger, setup_logging
from trading_bot.research.experiment_log import ExperimentLog
from trading_bot.research.experiments import generate_synthetic_bars, run_signal_smoke_experiment
from trading_bot.strategies.momentum import SimpleMomentum


def main() -> int:
    config = load_config()
    setup_logging(config)
    log = get_logger("research")

    log.info("Phase 1 smoke experiment: SimpleMomentum on synthetic random-walk data")
    strategy = SimpleMomentum({"lookback": 20, "threshold": 0.0})
    bars = generate_synthetic_bars(n=2000, seed=42, market_id="SYNTH")
    exp_log = ExperimentLog(config.resolve(config.research.experiment_log))

    results = run_signal_smoke_experiment(
        strategy,
        bars,
        exp_log,
        dataset="synthetic_gbm(n=2000, seed=42, vol_per_bar=0.1%)",
        notes=(
            "Phase 1 pipeline smoke test on synthetic data. Validates "
            "data->strategy->evaluation->experiment-log plumbing only. "
            "No edge expected or claimed: the data is a random walk."
        ),
    )

    print("\n=== Phase 1 smoke experiment complete ===")
    print(f"experiment_id:        {results['experiment_id']}")
    print(f"bars processed:       {results['n_bars']}")
    print(f"signals generated:    {results['n_signals']}")
    print(f"signals evaluated:    {results['n_evaluated']}")
    hr = results["hit_rate"]
    mr = results["mean_next_bar_return"]
    print(f"next-bar hit rate:    {hr:.2%}" if hr is not None else "next-bar hit rate:    n/a")
    print(f"mean next-bar return: {mr:+.6%}" if mr is not None else "mean next-bar return: n/a")
    print(f"experiment log:       {exp_log.path}")
    print(
        "\nNOTE: synthetic random-walk data — a hit rate near 50% and mean "
        "return near zero are the EXPECTED, correct outcome. This run proves "
        "the pipeline works, not that any strategy is profitable. Real "
        "research starts in Phase 2 with real historical data."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
