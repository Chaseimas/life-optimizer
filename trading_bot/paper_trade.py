"""Entry point: PAPER trading session. No orders are routed anywhere.

Two feed modes:

  # Replay a stored dataset through the paper loop (works offline):
  python trading_bot/paper_trade.py --market SYNTH --interval 5m \\
      --strategy simple_momentum --replay

  # Live public market data, simulated fills (needs normal internet access):
  python trading_bot/paper_trade.py --market HL:BTC --interval 1m \\
      --strategy simple_momentum --live-data

The paper loop drives the exact same engine as the backtester (same signal
logic, risk engine, sizing, stops, cost models). Each session writes
trades.jsonl / state.json / result.json into its run directory; watch it
with:  python -m trading_bot.monitoring.dashboard --run-dir <dir>

Emergency stop from outside the process:  touch trading_bot/KILL_SWITCH
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trading_bot.backtesting.engine import BacktestConfig
from trading_bot.backtesting.report import format_report
from trading_bot.core.config import load_config
from trading_bot.core.market import get_market
from trading_bot.core.types import Venue
from trading_bot.data_pipeline.store import BarStore
from trading_bot.monitoring.alerts import build_alert_manager
from trading_bot.monitoring.logging import setup_logging
from trading_bot.paper.feeds import HyperliquidPollingFeed, ReplayFeed
from trading_bot.paper.paper_trader import PaperTrader
from trading_bot.risk.kill_switch import KillSwitch
from trading_bot.strategies.registry import make_strategy


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--market", required=True)
    p.add_argument("--interval", required=True)
    p.add_argument("--strategy", default="simple_momentum")
    p.add_argument("--params", default="{}")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--replay", action="store_true",
                      help="replay the stored processed dataset")
    mode.add_argument("--live-data", action="store_true",
                      help="poll live public market data (Hyperliquid markets only)")
    p.add_argument("--dataset", help="replay: stored dataset id (defaults to --market)")
    p.add_argument("--max-bars", type=int, default=None)
    p.add_argument("--equity", type=float, default=100_000.0)
    p.add_argument("--stop-atr", type=float, default=2.0)
    p.add_argument("--atr-period", type=int, default=14)
    p.add_argument("--run-dir", default=None,
                   help="session output dir (default: trading_bot/paper_runs/<UTC ts>)")
    args = p.parse_args(argv)

    config = load_config()
    setup_logging(config)
    spec = get_market(args.market, config)

    print("=" * 72)
    print(" PAPER TRADING — simulated fills on real or replayed data.")
    print(" No orders are sent to any venue. Live trading remains Phase 15,")
    print(" disabled, and gated behind explicit configuration.")
    print("=" * 72)

    if args.live_data:
        if spec.venue is not Venue.HYPERLIQUID:
            print("--live-data currently supports Hyperliquid markets only "
                  "(public candle API). MNQ live data requires a broker feed — Phase 13+.")
            return 1
        feed = HyperliquidPollingFeed(spec.symbol, args.interval, spec.market_id)
    else:
        store = BarStore(config.resolve(config.data.raw_dir),
                         config.resolve(config.data.processed_dir))
        df = store.load(args.dataset or args.market, args.interval, stage="processed")
        feed = ReplayFeed(df, spec.market_id)
        print(f"replaying {len(feed)} stored bars through the paper loop")

    run_dir = args.run_dir or (
        config.root / "paper_runs" /
        f"{spec.market_id.replace(':', '_')}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    )
    trader = PaperTrader(
        spec=spec,
        strategy=make_strategy(args.strategy, json.loads(args.params)),
        limits=config.risk,
        config=BacktestConfig(
            initial_equity=args.equity, stop_atr_mult=args.stop_atr,
            atr_period=args.atr_period,
        ),
        feed=feed,
        run_dir=run_dir,
        alerts=build_alert_manager(config),
        kill_switch=KillSwitch(manual_file=config.root / "KILL_SWITCH"),
    )
    result = trader.run(max_bars=args.max_bars)
    print(format_report(result))
    print(f"\nsession artifacts: {run_dir}")
    print(f"status view:       python -m trading_bot.monitoring.dashboard --run-dir {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
