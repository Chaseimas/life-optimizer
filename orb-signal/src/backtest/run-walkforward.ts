/**
 * WALK-FORWARD VALIDATION — the honest test.
 *
 * Year A (train): 2024-06-09 → 2025-06-09  — derive all filters here
 * Year B (test):  2025-06-10 → 2026-06-09  — run cold, no peeking
 *
 * Fixes vs prior backtests:
 *  - Timestamp-true ORB: requires bars at exactly 9:30..9:34 ET (kills sparse-data fake ranges)
 *  - Day integrity: >=330 bars/day and last bar >=15:50 ET, else day skipped for that ticker
 *  - Round-trip transaction costs per ticker, subtracted from every trade
 *  - No compounding fantasy: primary metric is R after costs
 *
 * Decision rules PRE-STATED (so we don't tune on year B):
 *  - winnersA  = ticker×dir combos with totalR > 0 in A and >=15 trades
 *  - strongA   = combos with totalR >= +5R in A and >=15 trades
 *  - MWF adopted only if Tue AND Thu are both negative in A
 */

import { ALPACA_REST_URL } from "@/lib/constants";
import type { AlpacaBar, Direction } from "@/lib/types";

const BT_TICKERS = [
  "SPY", "QQQ", "AAPL", "TSLA", "NVDA", "AMD",
  "TQQQ", "UPRO", "SOXL", "FAS", "TNA",
  "MSTR", "COIN", "PLTR", "SMCI", "ARM", "MARA",
];

const START_DATE = "2024-06-09";
const SPLIT_DATE = "2025-06-10"; // < SPLIT = period A, >= SPLIT = period B
const END_DATE = "2026-06-09";

const ORB_MINUTES = 5;
const TARGET_R = 3;
const MIN_BODY_FRAC = 0.1;
const ENTRY_CUTOFF_MIN = 10 * 60 + 30; // 10:30 ET
const MIN_BARS_PER_DAY = 330;
const LAST_BAR_MIN = 15 * 60 + 50;     // 15:50 ET

// Round-trip cost as fraction of price (spread + slippage, both sides)
const COST_PCT: Record<string, number> = {
  SPY: 0.0001, QQQ: 0.0001,
  TQQQ: 0.0002, SOXL: 0.0002, UPRO: 0.0002, TNA: 0.0003, FAS: 0.0005,
  AAPL: 0.0002, TSLA: 0.0002, NVDA: 0.0002, AMD: 0.0002,
  PLTR: 0.0003, MARA: 0.0004, MSTR: 0.0005, COIN: 0.0004, SMCI: 0.0005, ARM: 0.0005,
};

function headers() {
  return {
    "APCA-API-KEY-ID": process.env.ALPACA_API_KEY!,
    "APCA-API-SECRET-KEY": process.env.ALPACA_API_SECRET!,
  };
}

async function fetchStockBars(symbol: string, timeframe: string, start: string, end: string): Promise<AlpacaBar[]> {
  const all: AlpacaBar[] = [];
  let pageToken: string | null = null;
  do {
    const params = new URLSearchParams({
      symbols: symbol, timeframe, start, end, limit: "10000", sort: "asc", feed: "iex",
    });
    if (pageToken) params.set("page_token", pageToken);
    const res = await fetch(`${ALPACA_REST_URL}/v2/stocks/bars?${params}`, { headers: headers() });
    if (!res.ok) { console.error(`  [${symbol}] ${res.status}`); return all; }
    const data = await res.json();
    all.push(...(data.bars?.[symbol] ?? []));
    pageToken = data.next_page_token ?? null;
    if (pageToken) await new Promise(r => setTimeout(r, 150));
  } while (pageToken);
  return all;
}

function etOffset(d: Date): number {
  const m = d.getUTCMonth(), day = d.getUTCDate();
  if (m < 2 || m > 10) return 5;
  if (m > 2 && m < 10) return 4;
  if (m === 2) return day >= 9 ? 4 : 5;
  return day < 2 ? 4 : 5;
}

function minuteET(bar: AlpacaBar): number {
  const d = new Date(bar.t);
  return (d.getUTCHours() - etOffset(d)) * 60 + d.getUTCMinutes();
}

function barDateET(bar: AlpacaBar): string {
  const d = new Date(bar.t);
  const et = new Date(d.getTime() - etOffset(d) * 3600000);
  return et.toISOString().split("T")[0];
}

interface WTrade {
  date: string;
  ticker: string;
  direction: Direction;
  entryPrice: number;
  risk: number;
  riskPctOfPrice: number;
  rMultiple: number;     // AFTER costs
  exitType: string;
  dow: number;           // 1=Mon..5=Fri
  period: "A" | "B";
}

interface DayIntegrity { totalDays: number; passedDays: number; }

function simulateTickerDay(date: string, ticker: string, bars: AlpacaBar[], targetR: number = TARGET_R): WTrade | null {
  // Integrity: enough coverage and a real close
  if (bars.length < MIN_BARS_PER_DAY) return null;
  if (minuteET(bars[bars.length - 1]) < LAST_BAR_MIN) return null;
  // Timestamp-true ORB: first 5 bars must be exactly 9:30..9:34
  for (let i = 0; i < ORB_MINUTES; i++) {
    if (i >= bars.length || minuteET(bars[i]) !== 570 + i) return null;
  }

  const rb = bars.slice(0, ORB_MINUTES);
  const rangeHigh = Math.max(...rb.map(b => b.h));
  const rangeLow = Math.min(...rb.map(b => b.l));
  const rangeWidth = rangeHigh - rangeLow;
  if (rangeWidth <= 0) return null;

  const firstOpen = rb[0].o;
  const firstClose = rb[ORB_MINUTES - 1].c;
  if (Math.abs(firstClose - firstOpen) < rangeWidth * MIN_BODY_FRAC) return null;
  const dir: Direction = firstClose > firstOpen ? "LONG" : "SHORT";

  // Entry: first 1-min close beyond the range in candle direction, before 10:30
  let entryBar = -1, entryPrice = 0;
  for (let i = ORB_MINUTES; i < bars.length; i++) {
    if (minuteET(bars[i]) > ENTRY_CUTOFF_MIN) break;
    const b = bars[i];
    if (dir === "LONG" && b.c > rangeHigh) { entryBar = i; entryPrice = b.c; break; }
    if (dir === "SHORT" && b.c < rangeLow) { entryBar = i; entryPrice = b.c; break; }
  }
  if (entryBar < 0) return null;

  const stopPrice = dir === "LONG" ? rangeLow : rangeHigh;
  const risk = dir === "LONG" ? entryPrice - stopPrice : stopPrice - entryPrice;
  if (risk <= 0) return null;

  const hasTarget = Number.isFinite(targetR);
  const targetPrice = dir === "LONG" ? entryPrice + targetR * risk : entryPrice - targetR * risk;

  // Exit: stop checked before target (conservative), else EOD close
  let exitPrice = bars[bars.length - 1].c;
  let exitType = "eod";
  for (let i = entryBar + 1; i < bars.length; i++) {
    const b = bars[i];
    if (dir === "LONG") {
      if (b.l <= stopPrice) { exitPrice = stopPrice; exitType = "stop"; break; }
      if (hasTarget && b.h >= targetPrice) { exitPrice = targetPrice; exitType = "target"; break; }
    } else {
      if (b.h >= stopPrice) { exitPrice = stopPrice; exitType = "stop"; break; }
      if (hasTarget && b.l <= targetPrice) { exitPrice = targetPrice; exitType = "target"; break; }
    }
  }

  const pnl = dir === "LONG" ? exitPrice - entryPrice : entryPrice - exitPrice;
  const costR = (entryPrice * (COST_PCT[ticker] ?? 0.0004)) / risk;
  const rMul = pnl / risk - costR;

  const dow = new Date(date + "T12:00:00Z").getUTCDay();
  return {
    date, ticker, direction: dir, entryPrice, risk,
    riskPctOfPrice: risk / entryPrice,
    rMultiple: rMul, exitType, dow,
    period: date < SPLIT_DATE ? "A" : "B",
  };
}

function metrics(trades: WTrade[]) {
  const n = trades.length;
  if (n === 0) return { n: 0, wr: 0, totalR: 0, avgR: 0, pf: 0, maxDD: 0 };
  const wins = trades.filter(t => t.rMultiple > 0.2).length;
  const totalR = trades.reduce((s, t) => s + t.rMultiple, 0);
  const gw = trades.filter(t => t.rMultiple > 0).reduce((s, t) => s + t.rMultiple, 0);
  const gl = Math.abs(trades.filter(t => t.rMultiple < 0).reduce((s, t) => s + t.rMultiple, 0));
  const pf = gl > 0 ? gw / gl : 0;
  let cum = 0, peak = 0, maxDD = 0;
  for (const t of [...trades].sort((a, b) => a.date.localeCompare(b.date))) {
    cum += t.rMultiple;
    if (cum > peak) peak = cum;
    if (peak - cum > maxDD) maxDD = peak - cum;
  }
  return { n, wr: (wins / n) * 100, totalR, avgR: totalR / n, pf, maxDD };
}

function printRow(name: string, m: ReturnType<typeof metrics>) {
  console.log(
    `  ${name.padEnd(30)} ${String(m.n).padEnd(6)} ${(m.wr.toFixed(0) + "%").padEnd(6)} ` +
    `${((m.avgR >= 0 ? "+" : "") + m.avgR.toFixed(3) + "R").padEnd(9)} ` +
    `${((m.totalR >= 0 ? "+" : "") + m.totalR.toFixed(1) + "R").padEnd(9)} ` +
    `${(m.pf.toFixed(2) + "x").padEnd(7)} -${m.maxDD.toFixed(1)}R`
  );
}

async function main() {
  if (!process.env.ALPACA_API_KEY) throw new Error("Set ALPACA_API_KEY");

  console.log("[walkforward] Train: 2024-06-09 → 2025-06-09 | Test: 2025-06-10 → 2026-06-09");
  console.log("[walkforward] Costs ON, timestamp-true ORB, day-integrity gates ON\n");

  console.log("[walkforward] Fetching 1-min bars...");
  // Target-rule A/B: 3R cap (current engine), 10R (near-paper), no target (pure EOD hold)
  const TARGET_VARIANTS: { label: string; r: number }[] = [
    { label: "3R target", r: 3 },
    { label: "10R target", r: 10 },
    { label: "no target (EOD only)", r: Infinity },
  ];
  const tradesByVariant = new Map<string, WTrade[]>(TARGET_VARIANTS.map(v => [v.label, []]));
  const trades: WTrade[] = tradesByVariant.get("3R target")!; // baseline used for combo analysis
  const integrity = new Map<string, DayIntegrity>();
  const riskPcts = new Map<string, number[]>();

  for (const ticker of BT_TICKERS) {
    const bars = await fetchStockBars(ticker, "1Min", START_DATE, END_DATE);

    // group by ET date, market hours only
    const byDate = new Map<string, AlpacaBar[]>();
    for (const bar of bars) {
      const min = minuteET(bar);
      if (min < 570 || min >= 960) continue;
      const d = barDateET(bar);
      if (!byDate.has(d)) byDate.set(d, []);
      byDate.get(d)!.push(bar);
    }

    let passed = 0;
    for (const [date, dayBars] of byDate) {
      for (const v of TARGET_VARIANTS) {
        const t = simulateTickerDay(date, ticker, dayBars, v.r);
        if (!t) break; // entry conditions identical across variants — if one is null, all are
        tradesByVariant.get(v.label)!.push(t);
        if (v.r === 3) {
          passed++;
          if (!riskPcts.has(ticker)) riskPcts.set(ticker, []);
          riskPcts.get(ticker)!.push(t.riskPctOfPrice);
        }
      }
    }
    integrity.set(ticker, { totalDays: byDate.size, passedDays: passed });
    console.log(`  ${ticker.padEnd(6)} ${bars.length} bars, ${byDate.size} days, ${passed} clean trade-days`);
  }

  const A = trades.filter(t => t.period === "A");
  const B = trades.filter(t => t.period === "B");

  // ── Derive filters from A ONLY ──
  const comboA = new Map<string, { r: number; n: number }>();
  for (const t of A) {
    const k = `${t.ticker} ${t.direction}`;
    if (!comboA.has(k)) comboA.set(k, { r: 0, n: 0 });
    const c = comboA.get(k)!;
    c.r += t.rMultiple; c.n++;
  }
  const winnersA = new Set([...comboA].filter(([, v]) => v.r > 0 && v.n >= 15).map(([k]) => k));
  const strongA = new Set([...comboA].filter(([, v]) => v.r >= 5 && v.n >= 15).map(([k]) => k));

  const dowR = new Map<number, number>();
  for (const t of A) dowR.set(t.dow, (dowR.get(t.dow) ?? 0) + t.rMultiple);
  const mwfAdopted = (dowR.get(2) ?? 0) < 0 && (dowR.get(4) ?? 0) < 0;

  // ── Report ──
  console.log("\n══ PERIOD A (train year) — combos derived here ══");
  console.log(`  ${"COMBO".padEnd(14)} ${"N".padEnd(5)} A-totalR`);
  const sortedCombos = [...comboA].sort((a, b) => b[1].r - a[1].r);
  const comboB = new Map<string, { r: number; n: number }>();
  for (const t of B) {
    const k = `${t.ticker} ${t.direction}`;
    if (!comboB.has(k)) comboB.set(k, { r: 0, n: 0 });
    const c = comboB.get(k)!;
    c.r += t.rMultiple; c.n++;
  }

  console.log("\n══ COMBO PERSISTENCE: A rank vs B result (the overfitting test) ══");
  console.log(`  ${"COMBO".padEnd(14)} ${"A totalR".padEnd(10)} B totalR`);
  let top10PositiveInB = 0;
  sortedCombos.forEach(([k, v], idx) => {
    const b = comboB.get(k);
    const bR = b?.r ?? 0;
    if (idx < 10 && bR > 0) top10PositiveInB++;
    console.log(`  ${k.padEnd(14)} ${((v.r >= 0 ? "+" : "") + v.r.toFixed(1) + "R (" + v.n + ")").padEnd(14)} ${(bR >= 0 ? "+" : "") + bR.toFixed(1)}R (${b?.n ?? 0})`);
  });
  console.log(`\n  Top-10 A-combos still positive in B: ${top10PositiveInB}/10`);

  console.log("\n══ DAY OF WEEK in A ══");
  const dows = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri"];
  for (let d = 1; d <= 5; d++) {
    console.log(`  ${dows[d]}: ${((dowR.get(d) ?? 0) >= 0 ? "+" : "")}${(dowR.get(d) ?? 0).toFixed(1)}R`);
  }
  console.log(`  MWF rule adopted from A? ${mwfAdopted ? "YES (Tue & Thu both negative)" : "NO"}`);

  console.log("\n══ YEAR B (cold test) — all filters derived from A only ══");
  console.log(`  ${"CONFIG".padEnd(30)} ${"N".padEnd(6)} ${"WIN%".padEnd(6)} ${"AVG R".padEnd(9)} ${"TOTAL R".padEnd(9)} ${"PF".padEnd(7)} MaxDD`);
  console.log("  " + "─".repeat(82));
  printRow("B: all combos (control)", metrics(B));
  printRow("B: winnersA only", metrics(B.filter(t => winnersA.has(`${t.ticker} ${t.direction}`))));
  printRow("B: strongA only", metrics(B.filter(t => strongA.has(`${t.ticker} ${t.direction}`))));
  printRow("B: all + MWF", metrics(B.filter(t => t.dow === 1 || t.dow === 3 || t.dow === 5)));
  printRow("B: winnersA + MWF", metrics(B.filter(t => winnersA.has(`${t.ticker} ${t.direction}`) && (t.dow === 1 || t.dow === 3 || t.dow === 5))));
  console.log("\n  For reference, same configs measured on A (in-sample, inflated):");
  printRow("A: all combos", metrics(A));
  printRow("A: winnersA only", metrics(A.filter(t => winnersA.has(`${t.ticker} ${t.direction}`))));

  // ── Target-rule A/B on the cold year ──
  console.log("\n══ TARGET RULE A/B — year B, all combos, after costs ══");
  console.log(`  ${"VARIANT".padEnd(30)} ${"N".padEnd(6)} ${"WIN%".padEnd(6)} ${"AVG R".padEnd(9)} ${"TOTAL R".padEnd(9)} ${"PF".padEnd(7)} MaxDD`);
  console.log("  " + "─".repeat(82));
  for (const [label, vTrades] of tradesByVariant) {
    printRow(`B: ${label}`, metrics(vTrades.filter(t => t.period === "B")));
  }
  console.log("  (A-year for context:)");
  for (const [label, vTrades] of tradesByVariant) {
    printRow(`A: ${label}`, metrics(vTrades.filter(t => t.period === "A")));
  }

  console.log("\n══ DATA INTEGRITY (clean days / total days) ══");
  for (const ticker of BT_TICKERS) {
    const i = integrity.get(ticker)!;
    const pct = i.totalDays > 0 ? (i.passedDays / i.totalDays) * 100 : 0;
    const rp = (riskPcts.get(ticker) ?? []).sort((a, b) => a - b);
    const medRisk = rp.length > 0 ? rp[Math.floor(rp.length / 2)] : 0;
    const leverageAt1Pct = medRisk > 0 ? 0.01 / medRisk : 0;
    console.log(`  ${ticker.padEnd(6)} ${String(i.passedDays).padEnd(5)}/${String(i.totalDays).padEnd(5)} (${pct.toFixed(0)}%)  median stop: ${(medRisk * 100).toFixed(2)}% of price → ${leverageAt1Pct.toFixed(1)}x notional needed at 1% risk`);
  }

  console.log("\n[walkforward] Done. Year-B numbers after costs are the honest expectation.");
}

main().catch(console.error);
