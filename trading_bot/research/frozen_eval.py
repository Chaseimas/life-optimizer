"""Pre-registered frozen-candidate evaluation (Pass 3).

Runs a frozen candidate — exactly as frozen, no knobs — on data that arrived
AFTER its out-of-sample boundary, and scores it against the criteria that
were pre-registered at freeze time. There are deliberately no parameters to
tune here: the only inputs are the candidate name and (optionally) an end
date.

Peek accounting: every invocation is written to the experiment log. Running
before the planned evaluation date is allowed but is labeled EARLY PEEK in
the output and in the log — repeatedly peeking until a favorable number
appears is exactly the failure mode this makes visible.

Usage:
    python -m trading_bot.research.frozen_eval --candidate orb_eth_15m_maker_p2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd

from trading_bot.backtesting.engine import BacktestEngine
from trading_bot.core.config import load_config
from trading_bot.core.market import get_market
from trading_bot.core.types import Side
from trading_bot.data_pipeline.frames import frame_to_bars
from trading_bot.data_pipeline.store import BarStore
from trading_bot.monitoring.logging import setup_logging
from trading_bot.research.controls import run_random_entry_control
from trading_bot.research.experiment_log import ExperimentLog
from trading_bot.research.frozen import (
    definition_hash,
    frozen_backtest_config,
    frozen_risk_limits,
    get_frozen,
)
from trading_bot.research.walkforward import _WarmupGate
from trading_bot.strategies.registry import make_strategy

WARMUP_BARS = 100  # bars before oos_start fed through the signal gate (indicators
                   # warm up; the gate makes trading on them impossible)


def _build_strategy(frozen: dict, funding):
    """Construct the frozen strategy. Strategies needing non-parameter inputs
    (funding series) are handled explicitly — never through hidden state."""
    if frozen["strategy"] == "funding_carry":
        from trading_bot.strategies.funding_carry import FundingCarry

        if funding is None:
            raise ValueError(
                "funding_carry evaluation requires stored funding history for "
                f"{frozen['market']} — accumulate it first"
            )
        return FundingCarry(dict(frozen["params"]), funding=funding)
    return make_strategy(frozen["strategy"], dict(frozen["params"]))


def evaluate(candidate_name: str, *, as_of: str | None = None,
             skip_control: bool = False, log_experiment: bool = True,
             store: BarStore | None = None) -> dict:
    frozen = get_frozen(candidate_name)
    config = load_config()
    store = store or BarStore(config.resolve(config.data.raw_dir),
                              config.resolve(config.data.processed_dir))

    market, interval = frozen["market"], frozen["interval"]
    spec = get_market(market, config)
    limits = frozen_risk_limits(candidate_name)
    df = store.load(market, interval, stage="processed")
    try:
        funding = store.load_funding(market)
    except FileNotFoundError:
        funding = None

    oos_start = pd.Timestamp(frozen["oos_start"])
    now = pd.Timestamp.now(tz="UTC")
    planned = pd.Timestamp(frozen["planned_evaluation_date"], tz="UTC")
    end = pd.Timestamp(as_of, tz="UTC") if as_of else df.index[-1]
    early_peek = now < planned

    oos_df = df[(df.index > oos_start) & (df.index <= end)]
    warmup_df = df[df.index <= oos_start].tail(WARMUP_BARS)
    run_df = pd.concat([warmup_df, oos_df])

    out: dict = {
        "candidate": candidate_name,
        "definition_sha256": definition_hash(candidate_name),
        "oos_start": str(oos_start),
        "oos_end": str(end),
        "oos_bars": len(oos_df),
        "oos_days": (round((oos_df.index[-1] - oos_df.index[0]).total_seconds() / 86400, 1)
                     if len(oos_df) else 0.0),
        "planned_evaluation_date": frozen["planned_evaluation_date"],
        "early_peek": early_peek,
        "scenarios": {},
    }

    if len(oos_df) == 0:
        out["verdict"] = "NO OOS DATA YET — accumulate data and return later"
        return _finish(out, frozen, config, log_experiment)

    bars = frame_to_bars(run_df, market)
    live_from = bars[len(warmup_df)].ts if len(oos_df) else None
    criteria = frozen["evaluation_criteria"]
    scenario_results = {}
    for scenario in frozen["maker_scenarios"]:
        strategy = _build_strategy(frozen, funding)
        gated = _WarmupGate(strategy, live_from=live_from)
        bt_config = frozen_backtest_config(candidate_name, scenario)
        engine = BacktestEngine(spec, gated, limits, bt_config, funding=funding)
        result = engine.run(bars)
        for t in result.trades:
            if t.entry_ts < live_from:
                raise AssertionError("frozen eval leak: trade entered before oos_start")
        m = result.metrics
        entry = {
            "net": round(m["trade_net_profit"], 2),
            "trades": m["trade_n_trades"],
            "profit_factor": m["trade_profit_factor"],
            "sharpe": round(m["sharpe"], 3),
            "max_dd_pct": round(m["max_drawdown_pct"], 4),
            "win_rate": m["trade_win_rate"],
            "fees": round(m["total_fees"], 2),
            "fill_rate": m["maker"]["fill_rate"],
            "missed": m["maker"]["missed_expired"],
            "long_net": round(m["long"]["net_profit"], 2),
            "short_net": round(m["short"]["net_profit"], 2),
        }
        scenario_results[scenario] = (result, entry)
        out["scenarios"][scenario] = entry

    # ---- pre-registered criteria, evaluated as written -----------------------
    n_trades = min(e["trades"] for _, e in scenario_results.values())
    checks = {"min_oos_trades": n_trades >= criteria["min_oos_trades"]}
    for s in criteria["require_positive_net_in_scenarios"]:
        checks[f"net_positive_{s}"] = out["scenarios"][s]["net"] > 0

    if not skip_control and n_trades > 0:
        base_result, _ = scenario_results["baseline"]
        bt_cfg = frozen_backtest_config(candidate_name, "baseline")
        mode = criteria.get("beta_control_mode", "long_only")

        def control_for(directions):
            return run_random_entry_control(
                spec=spec, bars=bars, trades=base_result.trades,
                bt_config=bt_cfg, limits=limits, funding=funding,
                directions=directions,
                n_replicates=criteria["beta_control_replicates"],
                seed=criteria["beta_control_seed"],
            )

        if mode == "long_only":
            longs = [t for t in base_result.trades if t.direction is Side.LONG]
            if longs:
                control = control_for((Side.LONG,))
                out["long_only_beta_control"] = control.describe()
                checks["long_only_control_ge_95"] = (
                    control.actual_percentile
                    >= criteria["long_only_beta_control_min_percentile"]
                )
            else:
                checks["long_only_control_ge_95"] = False
                out["long_only_beta_control"] = "no long trades in OOS window"
        elif mode == "mixed_and_sides":
            controls = {}
            ok = True
            mixed = control_for((Side.LONG, Side.SHORT))
            controls["mixed"] = mixed.describe()
            ok &= mixed.actual_percentile >= criteria["mixed_beta_control_min_percentile"]
            for label, side in (("long", Side.LONG), ("short", Side.SHORT)):
                if any(t.direction is side for t in base_result.trades):
                    c = control_for((side,))
                    controls[label] = c.describe()
                    ok &= (c.actual_percentile
                           >= criteria["side_beta_control_min_percentile"])
                else:
                    controls[label] = f"no {label} trades in OOS window"
                    ok = False
            out["beta_controls"] = controls
            checks["beta_controls_meet_preregistered_bars"] = bool(ok)
        else:
            raise ValueError(f"unknown beta_control_mode {mode!r}")

    out["criteria_checks"] = checks
    if not checks["min_oos_trades"]:
        out["verdict"] = (
            f"INSUFFICIENT DATA ({n_trades} OOS trades < "
            f"{criteria['min_oos_trades']}) — "
            f"{criteria['if_min_trades_not_met']}"
        )
    elif all(checks.values()):
        out["verdict"] = (
            "ALL PRE-REGISTERED CRITERIA MET on this OOS window. This is one "
            "positive independent observation — extend the record before any "
            "further conclusion. Live trading remains unauthorized."
        )
    else:
        failed = [k for k, ok in checks.items() if not ok]
        out["verdict"] = f"CRITERIA NOT MET ({', '.join(failed)}) — no edge demonstrated"
    return _finish(out, frozen, config, log_experiment)


def _finish(out: dict, frozen: dict, config, log_experiment: bool) -> dict:
    if log_experiment:
        exp_log = ExperimentLog(config.resolve(config.research.experiment_log))
        exp_log.log(
            strategy=frozen["strategy"], market=frozen["market"],
            params=dict(frozen["params"]),
            dataset=f"{frozen['market']}@{frozen['interval']} FROZEN OOS "
                    f"{out['oos_start']}..{out['oos_end']}",
            test_period=f"{out['oos_start']}..{out['oos_end']}",
            results={**out, "execution_assumptions": frozen["maker_scenarios"]},
            notes=("frozen_oos_evaluation EARLY PEEK" if out["early_peek"]
                   else "frozen_oos_evaluation (pre-registered)"),
        )
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--candidate", default="orb_eth_15m_maker_p2")
    p.add_argument("--as-of", default=None, help="evaluate OOS window up to this date")
    p.add_argument("--skip-control", action="store_true",
                   help="skip the (slow) beta control — result is then partial")
    args = p.parse_args(argv)

    config = load_config()
    setup_logging(config)
    out = evaluate(args.candidate, as_of=args.as_of, skip_control=args.skip_control)

    print("=" * 72)
    print(f"FROZEN EVALUATION  {out['candidate']}  sha256 {out['definition_sha256'][:16]}…")
    if out["early_peek"]:
        print(f"*** EARLY PEEK: planned evaluation date is "
              f"{out['planned_evaluation_date']} — this run is informational, is "
              "logged as a peek, and does not count as the evaluation. ***")
    print(f"OOS window: {out['oos_start']} .. {out['oos_end']} "
          f"({out['oos_bars']} bars, {out['oos_days']} days)")
    for scenario, e in out.get("scenarios", {}).items():
        print(f"  [{scenario:12s}] net {e['net']:>10,.2f}  trades {e['trades']:>3d}  "
              f"PF {e['profit_factor'] if e['profit_factor'] else 'n/a'}  "
              f"sharpe {e['sharpe']:>6.2f}  fill {e['fill_rate']:.0%}  "
              f"long {e['long_net']:,.0f} / short {e['short_net']:,.0f}")
    if "long_only_beta_control" in out:
        print(f"  long-only control: {out['long_only_beta_control']}")
    if "criteria_checks" in out:
        print(f"  criteria: {out['criteria_checks']}")
    print(f"VERDICT: {out['verdict']}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
