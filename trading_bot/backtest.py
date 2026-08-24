"""Entry point: run an event-driven backtest on a stored dataset.

Usage (from the repo root, venv active):

  python trading_bot/backtest.py --market HL:BTC --interval 1h \\
      --strategy simple_momentum --params '{"lookback": 24}' --stop-atr 2.0

  # synthetic pipeline check (data from: fetch synthetic):
  python trading_bot/backtest.py --market SYNTH --interval 5m --strategy simple_momentum

Every run prints the full report and appends a record to the experiment log
(use --no-log only for throwaway smoke checks). Data must exist in
data/processed first — see `python -m trading_bot.data_pipeline.fetch --help`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading_bot.backtesting.engine import BacktestConfig, BacktestEngine
from trading_bot.backtesting.report import format_report
from trading_bot.core.config import load_config
from trading_bot.core.market import get_market
from trading_bot.data_pipeline.frames import frame_to_bars
from trading_bot.data_pipeline.store import BarStore
from trading_bot.monitoring.logging import get_logger, setup_logging
from trading_bot.research.experiment_log import ExperimentLog
from trading_bot.strategies.registry import make_strategy

REPORT_METRIC_KEYS = [
    "trade_n_trades", "trade_net_profit", "trade_profit_factor", "trade_win_rate",
    "trade_expectancy", "sharpe", "sortino", "calmar", "max_drawdown_abs",
    "max_drawdown_pct", "daily_mean", "daily_median", "daily_std",
    "daily_pct_profitable_days", "daily_best_day", "daily_worst_day",
    "total_fees", "total_slippage_cost", "total_funding", "final_equity",
    "annualized_return_pct", "exit_reasons",
]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--market", required=True, help="MNQ | HL:BTC | HL:ETH | HL:SOL | SYNTH")
    p.add_argument("--dataset", help="stored dataset market id (defaults to --market)")
    p.add_argument("--interval", required=True, help="1m 5m 15m 30m 1h 4h 1d")
    p.add_argument("--strategy", default="simple_momentum")
    p.add_argument("--params", default="{}", help="strategy params as JSON")
    p.add_argument("--equity", type=float, default=100_000.0)
    p.add_argument("--risk-per-trade", type=float, default=None,
                   help="fraction of equity risked per trade (capped by config limit)")
    p.add_argument("--stop-points", type=float, default=None, help="fixed stop distance in points")
    p.add_argument("--tp-points", type=float, default=None)
    p.add_argument("--stop-atr", type=float, default=2.0, help="stop = k * ATR (default path)")
    p.add_argument("--tp-atr", type=float, default=None)
    p.add_argument("--atr-period", type=int, default=14)
    p.add_argument("--start", default=None, help="slice start (ISO date, UTC)")
    p.add_argument("--end", default=None, help="slice end (ISO date, UTC)")
    p.add_argument("--funding", action="store_true", help="apply stored funding history (perps)")
    p.add_argument("--long-only", action="store_true")
    p.add_argument("--no-log", action="store_true", help="skip the experiment log (smoke checks only)")
    p.add_argument("--tag", default="", help="free-form note for the experiment log")
    p.add_argument("--mc", type=int, default=0, metavar="N",
                   help="run N Monte Carlo resamples of the trade sequence (0 = off)")
    p.add_argument("--mc-method", default="shuffle", choices=["shuffle", "bootstrap"])
    args = p.parse_args(argv)

    config = load_config()
    setup_logging(config)
    log = get_logger("backtest")

    spec = get_market(args.market, config)
    dataset_id = args.dataset or args.market
    store = BarStore(config.resolve(config.data.raw_dir), config.resolve(config.data.processed_dir))
    df = store.load(dataset_id, args.interval, stage="processed")
    if args.start:
        df = df.loc[args.start:]
    if args.end:
        df = df.loc[: args.end]
    if df.empty:
        print("Selected slice contains no bars.")
        return 1

    funding = None
    if args.funding:
        funding = store.load_funding(dataset_id)

    strategy = make_strategy(args.strategy, json.loads(args.params))
    bt_config = BacktestConfig(
        initial_equity=args.equity,
        risk_per_trade=args.risk_per_trade,
        fixed_stop_points=args.stop_points,
        fixed_tp_points=args.tp_points,
        stop_atr_mult=args.stop_atr,
        tp_atr_mult=args.tp_atr,
        atr_period=args.atr_period,
        allow_short=not args.long_only,
    )
    engine = BacktestEngine(spec, strategy, config.risk, bt_config, funding=funding)
    bars = frame_to_bars(df, spec.market_id)
    log.info("running backtest: %s on %s (%d bars)", strategy.name, spec.market_id, len(bars))
    result = engine.run(bars)

    print(format_report(result))

    mc_summary = None
    if args.mc > 0:
        from trading_bot.backtesting.monte_carlo import format_monte_carlo, monte_carlo_trades

        if len(result.trades) < 5:
            print("\nMonte Carlo skipped: fewer than 5 trades.")
        else:
            mc = monte_carlo_trades(
                result.trade_pnls, initial_equity=args.equity,
                n_sims=args.mc, method=args.mc_method,
            )
            print(format_monte_carlo(mc))
            mc_summary = {
                "method": mc.method, "n_sims": mc.n_sims,
                "drawdown_percentiles": mc.drawdown_percentiles,
                "final_pnl_percentiles": mc.final_pnl_percentiles,
                "prob_final_negative": mc.prob_final_negative,
                "losing_streak_percentiles": mc.losing_streak_percentiles,
                "prob_ruin": mc.prob_ruin, "ruin_drawdown": mc.ruin_drawdown,
            }

    meta = store.meta(dataset_id, args.interval, stage="processed")
    if "synthetic" in str(meta.get("source", "")):
        print("\nWARNING: this dataset is SYNTHETIC random-walk data. The numbers "
              "above validate the machinery only — they say nothing about real markets.")

    if not args.no_log:
        exp_log = ExperimentLog(config.resolve(config.research.experiment_log))
        record = exp_log.log(
            strategy=strategy.name,
            market=spec.market_id,
            params={
                **strategy.params,
                "_backtest": {
                    "equity": args.equity, "risk_per_trade": args.risk_per_trade,
                    "stop_points": args.stop_points, "tp_points": args.tp_points,
                    "stop_atr": args.stop_atr, "tp_atr": args.tp_atr,
                    "atr_period": args.atr_period, "long_only": args.long_only,
                    "funding": args.funding,
                },
            },
            dataset=f"{dataset_id}@{args.interval} source={meta.get('source', 'unknown')} "
                    f"span={df.index[0]}..{df.index[-1]} rows={len(df)}",
            results={
                **{k: result.metrics.get(k) for k in REPORT_METRIC_KEYS},
                **({"monte_carlo": mc_summary} if mc_summary else {}),
            },
            notes=args.tag or "single-period backtest (in-sample unless stated otherwise)",
        )
        print(f"\nexperiment logged: {record.experiment_id} -> {exp_log.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
