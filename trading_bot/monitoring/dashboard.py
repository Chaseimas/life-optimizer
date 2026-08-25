"""Paper-session status view (Phase 14).

Read-only by design: it renders the ``state.json`` a paper session writes
after every bar, plus the tail of its trade log. There are no controls here
that could bypass the risk engine — the dashboard observes, the risk engine
decides.

Usage:
    python -m trading_bot.monitoring.dashboard --run-dir trading_bot/paper_runs/<ts>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def format_status(state: dict, recent_trades: list[dict]) -> str:
    pos = state.get("position")
    lines = [
        "=" * 64,
        f"PAPER SESSION STATUS  [{state.get('market_id', '?')}]   mode={state.get('mode', '?')}",
        f"as of: {state.get('written_at', '?')}   last bar: {state.get('last_bar_ts', '-')}",
        "-" * 64,
        f"bars processed:     {state.get('n_bars', 0)}",
        f"equity (realized):  {state.get('equity_realized', 0):,.2f}",
        f"equity (mark):      {state.get('equity_mark_to_market') or 0:,.2f}",
        f"closed trades:      {state.get('n_trades', 0)}   today: {state.get('trades_today', 0)}",
        f"daily P&L:          {state.get('daily_pnl', 0):+,.2f}",
    ]
    if pos:
        lines.append(
            f"open position:      {pos['direction']} {pos['size']} @ {pos['entry_price']} "
            f"(stop {pos['stop_price']}, tp {pos['tp_price']}, "
            f"funding {pos['funding_paid']:+.2f}, {pos['bars_held']} bars)"
        )
    else:
        lines.append("open position:      none")
    halted = state.get("halted_for_day")
    lines.append(f"daily halt:         {halted or 'no'}")
    lines.append(
        "kill switch:        "
        + ("*** TRIPPED — trading halted ***" if state.get("kill_switch_tripped") else "armed, ok")
    )
    if state.get("halts"):
        lines.append("-" * 64)
        lines.append("risk events:")
        lines.extend(f"  {h}" for h in state["halts"][-5:])
    if recent_trades:
        lines.append("-" * 64)
        lines.append("last trades:")
        for t in recent_trades[-5:]:
            lines.append(
                f"  {t['exit_ts']}  {t['direction']:>5s} {t['size']}  "
                f"net {t['net_pnl']:+9.2f}  ({t['exit_reason']})"
            )
    lines.append("=" * 64)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir", required=True, help="paper session directory")
    args = p.parse_args(argv)
    run_dir = Path(args.run_dir)
    state_path = run_dir / "state.json"
    if not state_path.exists():
        print(f"No state file at {state_path} — is the session running / did it run?")
        return 1
    state = json.loads(state_path.read_text())
    trades: list[dict] = []
    trades_path = run_dir / "trades.jsonl"
    if trades_path.exists():
        with open(trades_path, "r", encoding="utf-8") as f:
            trades = [json.loads(line) for line in f if line.strip()]
    print(format_status(state, trades))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())
