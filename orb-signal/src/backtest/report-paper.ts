/**
 * Paper-trading readiness report — the go/no-go gate check.
 *
 * Run after the paper phase (`npm run report:paper`). Compares live paper results
 * against the walk-forward backtest expectation and prints a verdict:
 *   - KEEP COLLECTING (not enough trades yet)
 *   - GO            (gates passed — proceed per GOLIVE.md)
 *   - STOP          (edge not showing up live — diagnose before any money)
 */

import { getDb } from "@/lib/db/index";

// Walk-forward year-B reference (after costs) — what "matching" means
const REF = {
  avgR: 0.066,        // all-combos control
  winRate: 37,        // %
  maxSlippageR: 0.05, // gate: avg entry slippage must stay under this
  minTrades: 30,      // gate: sample size before any verdict
};

const STOCK_TICKERS = ["TQQQ", "SOXL", "TSLA", "NVDA", "AMD", "AAPL", "PLTR", "MARA", "SMCI", "MSTR", "SPY", "QQQ"];

interface Row {
  id: number; ticker: string; date: string; direction: string;
  entry_price: number; exit_price: number | null; exit_type: string | null;
  outcome: string | null; r_multiple: number | null; slippage_r: number | null;
}

function main() {
  const db = getDb();
  const placeholders = STOCK_TICKERS.map(() => "?").join(",");
  const rows = db.prepare(`
    SELECT id, ticker, date, direction, entry_price, exit_price, exit_type,
           outcome, r_multiple, slippage_r
    FROM signals
    WHERE was_selected = 1 AND timeframe = 5 AND ticker IN (${placeholders})
    ORDER BY date ASC, signal_time ASC
  `).all(...STOCK_TICKERS) as Row[];

  const closed = rows.filter(r => r.outcome !== null && r.r_multiple !== null);
  const open = rows.length - closed.length;

  console.log("╔════════════════════════════════════════════════════════════╗");
  console.log("║        PAPER TRADING READINESS REPORT — Stock ORB          ║");
  console.log("╚════════════════════════════════════════════════════════════╝\n");

  if (closed.length === 0) {
    console.log("  No completed paper trades yet. Let the engine run.");
    return;
  }

  const n = closed.length;
  const wins = closed.filter(r => r.outcome === "WIN").length;
  const losses = closed.filter(r => r.outcome === "LOSS").length;
  const scratches = closed.filter(r => r.outcome === "SCRATCH").length;
  const totalR = closed.reduce((s, r) => s + (r.r_multiple ?? 0), 0);
  const avgR = totalR / n;
  const winRate = (wins / n) * 100;
  const gw = closed.filter(r => (r.r_multiple ?? 0) > 0).reduce((s, r) => s + (r.r_multiple ?? 0), 0);
  const gl = Math.abs(closed.filter(r => (r.r_multiple ?? 0) < 0).reduce((s, r) => s + (r.r_multiple ?? 0), 0));
  const pf = gl > 0 ? gw / gl : 0;

  let cum = 0, peak = 0, maxDD = 0;
  for (const r of closed) {
    cum += r.r_multiple ?? 0;
    if (cum > peak) peak = cum;
    if (peak - cum > maxDD) maxDD = peak - cum;
  }

  const slips = closed.map(r => r.slippage_r).filter((s): s is number => s !== null);
  const avgSlip = slips.length > 0 ? slips.reduce((a, b) => a + b, 0) / slips.length : null;

  const days = new Set(closed.map(r => r.date)).size;
  const firstDate = closed[0].date, lastDate = closed[closed.length - 1].date;

  console.log(`  Period: ${firstDate} → ${lastDate} (${days} trading days)`);
  console.log(`  Trades: ${n} closed (${wins}W-${losses}L-${scratches}S)${open > 0 ? ` + ${open} open` : ""}\n`);

  const cmp = (live: number, ref: number, unit = "") =>
    `live ${live >= 0 ? "+" : ""}${live.toFixed(3)}${unit}  vs backtest ${ref >= 0 ? "+" : ""}${ref.toFixed(3)}${unit}`;

  console.log("  METRIC COMPARISON");
  console.log("  " + "─".repeat(56));
  console.log(`  Avg R/trade:   ${cmp(avgR, REF.avgR, "R")}`);
  console.log(`  Win rate:      live ${winRate.toFixed(1)}%  vs backtest ~${REF.winRate}%`);
  console.log(`  Total R:       ${totalR >= 0 ? "+" : ""}${totalR.toFixed(2)}R | PF ${pf.toFixed(2)}x | MaxDD -${maxDD.toFixed(2)}R`);
  console.log(`  Avg slippage:  ${avgSlip === null ? "n/a (no data yet)" : (avgSlip >= 0 ? "+" : "") + avgSlip.toFixed(4) + "R (gate: ≤ " + REF.maxSlippageR + "R)"}\n`);

  // Per ticker
  console.log("  BY TICKER");
  console.log("  " + "─".repeat(56));
  const tickers = [...new Set(closed.map(r => r.ticker))].sort();
  for (const t of tickers) {
    const tt = closed.filter(r => r.ticker === t);
    const tr = tt.reduce((s, r) => s + (r.r_multiple ?? 0), 0);
    const tw = tt.filter(r => r.outcome === "WIN").length;
    console.log(`  ${t.padEnd(7)} ${String(tt.length).padEnd(4)} ${(((tw / tt.length) * 100).toFixed(0) + "%").padEnd(6)} ${(tr >= 0 ? "+" : "") + tr.toFixed(2)}R`);
  }

  // Exit types
  console.log("\n  BY EXIT");
  console.log("  " + "─".repeat(56));
  for (const ex of ["target", "stop", "eod"]) {
    const tt = closed.filter(r => r.exit_type === ex);
    if (tt.length === 0) continue;
    const tr = tt.reduce((s, r) => s + (r.r_multiple ?? 0), 0);
    console.log(`  ${ex.padEnd(8)} ${String(tt.length).padEnd(4)} avg ${(tr / tt.length >= 0 ? "+" : "") + (tr / tt.length).toFixed(2)}R`);
  }

  // ── Verdict ──
  console.log("\n  VERDICT");
  console.log("  " + "═".repeat(56));

  if (n < REF.minTrades) {
    console.log(`  ⏳ KEEP COLLECTING — ${n}/${REF.minTrades} trades. No verdict yet.`);
    console.log(`     At the current pace that's roughly ${Math.ceil((REF.minTrades - n) / Math.max(n / days, 0.1) / 5)} more weeks.`);
    return;
  }

  const gates: { name: string; pass: boolean; detail: string }[] = [
    { name: "Sample size ≥ 30", pass: n >= REF.minTrades, detail: `${n} trades` },
    { name: "Avg R > 0", pass: avgR > 0, detail: `${avgR >= 0 ? "+" : ""}${avgR.toFixed(3)}R (backtest +${REF.avgR})` },
    { name: "Slippage ≤ 0.05R", pass: avgSlip === null || avgSlip <= REF.maxSlippageR, detail: avgSlip === null ? "no data" : `${avgSlip.toFixed(4)}R` },
    { name: "Win rate sane (25-55%)", pass: winRate >= 25 && winRate <= 55, detail: `${winRate.toFixed(1)}%` },
  ];

  for (const g of gates) {
    console.log(`  ${g.pass ? "✅" : "❌"} ${g.name.padEnd(26)} ${g.detail}`);
  }

  const allPass = gates.every(g => g.pass);
  console.log("  " + "─".repeat(56));
  if (allPass) {
    console.log("  ✅ GO — live results match the backtest. Proceed per GOLIVE.md.");
  } else if (avgR <= 0) {
    console.log("  ⛔ STOP — the edge is not showing up live. Do NOT put money on this.");
    console.log("     Diagnose: compare entry times/prices vs backtest, check slippage,");
    console.log("     check whether losses cluster in specific tickers, re-run walkforward.");
  } else {
    console.log("  ⚠️ MIXED — positive but a gate failed. Fix the failing gate, collect 2 more weeks.");
  }
}

main();
