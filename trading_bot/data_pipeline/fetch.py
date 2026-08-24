"""Data acquisition CLI (Phase 2/3): fetch or import, clean, store.

Usage (from the repo root, venv active):

  # Hyperliquid public candles + funding (needs normal internet access):
  python -m trading_bot.data_pipeline.fetch hyperliquid --coin BTC --interval 1h --days 200

  # Import an MNQ CSV (e.g. Databento OHLCV export, ts_event = ns epoch, bar-open):
  python -m trading_bot.data_pipeline.fetch csv --path mnq_1m.csv --market MNQ \\
      --interval 1m --ts-col ts_event --ts-semantics open --tz UTC

  # Synthetic random-walk bars (pipeline development only, clearly labeled):
  python -m trading_bot.data_pipeline.fetch synthetic --market SYNTH --interval 5m --bars 20000

  # Show what is stored:
  python -m trading_bot.data_pipeline.fetch catalog

Every fetch writes the untouched raw dataset AND a cleaned processed dataset
(with the cleaning audit printed), so backtests always run on audited data.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd

from trading_bot.core.config import load_config
from trading_bot.core.market import get_market
from trading_bot.data_pipeline import hyperliquid as hl
from trading_bot.data_pipeline.clean import clean_frame, filter_cme_session
from trading_bot.data_pipeline.csv_import import ColumnMap, import_csv
from trading_bot.data_pipeline.store import BarStore
from trading_bot.monitoring.logging import get_logger, setup_logging


def _store(config) -> BarStore:
    return BarStore(
        config.resolve(config.data.raw_dir), config.resolve(config.data.processed_dir)
    )


def _clean_and_save(df, *, market_id: str, interval: str, source: str, store: BarStore,
                    is_24_7: bool, session_filter: bool = False) -> None:
    store.save(df, market_id=market_id, interval=interval, stage="raw", source=source)
    if session_filter:
        df, srep = filter_cme_session(df)
        print(f"session filter: dropped {srep.session_rows_dropped} out-of-session bars")
    clean, rep = clean_frame(df, interval=interval, is_24_7=is_24_7)
    store.save(
        clean, market_id=market_id, interval=interval, stage="processed", source=source,
        notes=f"cleaned from {source}: {rep.summary()}",
    )
    print(f"CLEANED  {market_id} {interval}: {rep.summary()}")
    for note in rep.notes:
        print(f"  note: {note}")
    print(f"stored   raw + processed for {market_id} {interval} "
          f"({clean.index[0]} .. {clean.index[-1]}, {len(clean)} bars)")


def cmd_hyperliquid(args, config) -> int:
    market_id = f"HL:{args.coin.upper()}"
    get_market(market_id)  # validates it's a known market
    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.Timedelta(days=args.days)
    print(f"fetching {market_id} {args.interval} candles {start} .. {end} ...")
    df = hl.fetch_candles(args.coin.upper(), args.interval, start, end)
    if df.empty:
        print("No candles returned — nothing stored.")
        return 1
    store = _store(config)
    _clean_and_save(df, market_id=market_id, interval=args.interval,
                    source="hyperliquid_api", store=store, is_24_7=True)
    if args.funding:
        print("fetching funding history ...")
        s = hl.fetch_funding(args.coin.upper(), start, end)
        if len(s):
            p = store.save_funding(s, market_id)
            print(f"stored   {len(s)} hourly funding rates -> {p}")
        else:
            print("no funding rows returned")
    return 0


def cmd_csv(args, config) -> int:
    colmap = ColumnMap(
        ts=args.ts_col, tz=args.tz, ts_semantics=args.ts_semantics,
        interval=args.interval, price_scale=args.price_scale,
    )
    df = import_csv(args.path, colmap)
    session_filter = args.market.upper() == "MNQ" and not args.no_session_filter
    _clean_and_save(
        df, market_id=args.market, interval=args.interval,
        source=f"csv:{Path(args.path).name}", store=_store(config),
        is_24_7=not session_filter, session_filter=session_filter,
    )
    return 0


def cmd_synthetic(args, config) -> int:
    from trading_bot.research.experiments import generate_synthetic_bars
    from trading_bot.data_pipeline.frames import INTERVALS, bars_to_frame

    bars = generate_synthetic_bars(
        n=args.bars, seed=args.seed, market_id=args.market,
        freq_minutes=INTERVALS[args.interval] // 60,
    )
    _clean_and_save(
        bars_to_frame(bars), market_id=args.market, interval=args.interval,
        source=f"synthetic(seed={args.seed})", store=_store(config), is_24_7=True,
    )
    print("NOTE: synthetic random-walk data — for pipeline development only. "
          "Any measured edge on this data is noise by construction.")
    return 0


def cmd_catalog(args, config) -> int:
    entries = _store(config).catalog()
    if not entries:
        print("No datasets stored yet.")
        return 0
    for e in entries:
        print(f"[{e.get('stage', '?'):9s}] {e.get('market_id', '?'):8s} {e.get('interval', '?'):4s} "
              f"{e.get('rows', 0):>8d} bars  {e.get('start', '?')} .. {e.get('end', '?')}  "
              f"source={e.get('source', '?')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_hl = sub.add_parser("hyperliquid", help="fetch public HL candles/funding")
    p_hl.add_argument("--coin", required=True, help="BTC | ETH | SOL")
    p_hl.add_argument("--interval", default="1h", help="1m 5m 15m 30m 1h 4h 1d")
    p_hl.add_argument("--days", type=int, default=200)
    p_hl.add_argument("--funding", action="store_true", help="also fetch funding history")
    p_hl.set_defaults(fn=cmd_hyperliquid)

    p_csv = sub.add_parser("csv", help="import an OHLCV CSV (MNQ path)")
    p_csv.add_argument("--path", required=True)
    p_csv.add_argument("--market", required=True, help="e.g. MNQ")
    p_csv.add_argument("--interval", required=True)
    p_csv.add_argument("--ts-col", default="ts_event")
    p_csv.add_argument("--tz", default="UTC")
    p_csv.add_argument("--ts-semantics", default="open", choices=["open", "close"])
    p_csv.add_argument("--price-scale", type=float, default=1.0)
    p_csv.add_argument("--no-session-filter", action="store_true")
    p_csv.set_defaults(fn=cmd_csv)

    p_syn = sub.add_parser("synthetic", help="generate labeled synthetic data")
    p_syn.add_argument("--market", default="SYNTH")
    p_syn.add_argument("--interval", default="5m")
    p_syn.add_argument("--bars", type=int, default=20000)
    p_syn.add_argument("--seed", type=int, default=42)
    p_syn.set_defaults(fn=cmd_synthetic)

    p_cat = sub.add_parser("catalog", help="list stored datasets")
    p_cat.set_defaults(fn=cmd_catalog)

    args = parser.parse_args(argv)
    config = load_config()
    setup_logging(config)
    return args.fn(args, config)


if __name__ == "__main__":
    raise SystemExit(main())
