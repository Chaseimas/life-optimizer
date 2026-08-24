"""Entry point: rolling walk-forward analysis on a stored dataset.

Usage (from the repo root, venv active):

  python trading_bot/walkforward.py --market HL:BTC --interval 1h \\
      --strategy simple_momentum --grid '{"lookback": [12, 24, 48]}' \\
      --train-bars 2000 --test-bars 500

Parameters are chosen per-window on TRAIN data only; each TEST slice is
evaluated once; results are aggregated and logged to the experiment log
(including how many train experiments were burned — the multiple-testing
denominator).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading_bot.backtesting.engine import BacktestConfig
from trading_bot.core.config import load_config
from trading_bot.core.market import get_market
from trading_bot.data_pipeline.frames import frame_to_bars
from trading_bot.data_pipeline.store import BarStore
from trading_bot.monitoring.logging import setup_logging
from trading_bot.research.experiment_log import ExperimentLog
from trading_bot.research.walkforward import (
    expand_grid,
    format_walkforward_report,
    run_walkforward,
)

OOS_METRIC_KEYS = [
    "trade_n_trades", "trade_net_profit", "trade_profit_factor", "trade_win_rate",
    "trade_expectancy", "sharpe", "sortino", "max_drawdown_abs", "max_drawdown_pct",
    "daily_mean", "daily_median", "daily_std", "daily_pct_profitable_days",
    "final_equity",
]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--market", required=True)
    p.add_argument("--dataset", help="stored dataset id (defaults to --market)")
    p.add_argument("--interval", required=True)
    p.add_argument("--strategy", default="simple_momentum")
    p.add_argument("--grid", required=True,
                   help='JSON dict of lists, e.g. {"lookback": [12, 24, 48]}')
    p.add_argument("--train-bars", type=int, required=True)
    p.add_argument("--test-bars", type=int, required=True)
    p.add_argument("--step-bars", type=int, default=None)
    p.add_argument("--embargo-bars", type=int, default=0)
    p.add_argument("--metric", default="sharpe",
                   choices=["sharpe", "trade_net_profit", "sortino", "trade_expectancy"])
    p.add_argument("--equity", type=float, default=100_000.0)
    p.add_argument("--stop-atr", type=float, default=2.0)
    p.add_argument("--atr-period", type=int, default=14)
    p.add_argument("--no-log", action="store_true")
    p.add_argument("--tag", default="")
    args = p.parse_args(argv)

    config = load_config()
    setup_logging(config)

    spec = get_market(args.market, config)
    dataset_id = args.dataset or args.market
    store = BarStore(config.resolve(config.data.raw_dir), config.resolve(config.data.processed_dir))
    df = store.load(dataset_id, args.interval, stage="processed")
    bars = frame_to_bars(df, spec.market_id)

    grid = expand_grid(json.loads(args.grid))
    bt_config = BacktestConfig(
        initial_equity=args.equity, stop_atr_mult=args.stop_atr, atr_period=args.atr_period,
    )
    result = run_walkforward(
        spec=spec, strategy_name=args.strategy, grid=grid, bars=bars,
        limits=config.risk, bt_config=bt_config,
        train_bars=args.train_bars, test_bars=args.test_bars,
        step_bars=args.step_bars, embargo_bars=args.embargo_bars,
        selection_metric=args.metric,
    )
    print(format_walkforward_report(result))

    meta = store.meta(dataset_id, args.interval, stage="processed")
    if "synthetic" in str(meta.get("source", "")):
        print("\nWARNING: SYNTHETIC dataset — this run validates machinery, not markets.")

    if not args.no_log:
        exp_log = ExperimentLog(config.resolve(config.research.experiment_log))
        record = exp_log.log(
            strategy=args.strategy,
            market=spec.market_id,
            params={"grid": json.loads(args.grid), "selection_metric": args.metric,
                    "train_bars": args.train_bars, "test_bars": args.test_bars,
                    "embargo_bars": args.embargo_bars,
                    "_backtest": {"equity": args.equity, "stop_atr": args.stop_atr,
                                   "atr_period": args.atr_period}},
            dataset=f"{dataset_id}@{args.interval} source={meta.get('source', 'unknown')} "
                    f"rows={len(df)}",
            results={
                "n_windows": len(result.windows),
                "n_train_experiments": result.n_experiments,
                "chosen_params_history": result.chosen_params_history,
                "oos": {k: result.oos_metrics.get(k) for k in OOS_METRIC_KEYS},
            },
            notes=args.tag or "walk-forward: params chosen on train only; aggregated OOS",
        )
        print(f"\nexperiment logged: {record.experiment_id} -> {exp_log.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
