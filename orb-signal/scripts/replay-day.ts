/**
 * Replay a single day through the engine's exact rules — used to answer
 * "what would have happened" for a missed session. Usage:
 *   npx tsx --env-file=.env.local scripts/replay-day.ts [YYYY-MM-DD]
 */
import { ALPACA_REST_URL } from "../src/lib/constants";
import { STOCKS_CONFIG as CFG } from "../src/engine-stocks/config";
import type { AlpacaBar, Direction } from "../src/lib/types";

const DATE = process.argv[2] ?? new Date().toISOString().split("T")[0];

function headers() {
  return {
    "APCA-API-KEY-ID": process.env.ALPACA_API_KEY!,
    "APCA-API-SECRET-KEY": process.env.ALPACA_API_SECRET!,
  };
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

async function fetchDay(symbol: string): Promise<AlpacaBar[]> {
  const params = new URLSearchParams({
    symbols: symbol, timeframe: "1Min",
    start: `${DATE}T08:00:00-04:00`, end: `${DATE}T17:00:00-04:00`,
    limit: "10000", feed: "iex", sort: "asc",
  });
  const res = await fetch(`${ALPACA_REST_URL}/v2/stocks/bars?${params}`, { headers: headers() });
  if (!res.ok) return [];
  const data = await res.json();
  return (data.bars?.[symbol] ?? []).filter((b: AlpacaBar) => {
    const m = minuteET(b);
    return m >= 570 && m < 960;
  });
}

interface Sim {
  ticker: string; direction: Direction;
  entryBarMin: number; entryPrice: number; stopPrice: number; targetPrice: number;
  risk: number; exitPrice: number; exitType: string; exitBarMin: number; r: number;
}

function simulate(ticker: string, bars: AlpacaBar[]): Sim | null {
  if (bars.length < 40) return null;
  for (let i = 0; i < CFG.ORB_MINUTES; i++) {
    if (i >= bars.length || minuteET(bars[i]) !== 570 + i) return null;
  }
  const rb = bars.slice(0, CFG.ORB_MINUTES);
  const rangeHigh = Math.max(...rb.map(b => b.h));
  const rangeLow = Math.min(...rb.map(b => b.l));
  const rangeWidth = rangeHigh - rangeLow;
  if (rangeWidth <= 0) return null;
  const body = Math.abs(rb[CFG.ORB_MINUTES - 1].c - rb[0].o);
  if (body < rangeWidth * CFG.MIN_BODY_FRAC) return null;
  const dir: Direction = rb[CFG.ORB_MINUTES - 1].c > rb[0].o ? "LONG" : "SHORT";

  let entryBar = -1, entryPrice = 0;
  for (let i = CFG.ORB_MINUTES; i < bars.length; i++) {
    if (minuteET(bars[i]) > CFG.ENTRY_CUTOFF_MIN) break;
    const b = bars[i];
    if (dir === "LONG" && b.c > rangeHigh) { entryBar = i; entryPrice = b.c; break; }
    if (dir === "SHORT" && b.c < rangeLow) { entryBar = i; entryPrice = b.c; break; }
  }
  if (entryBar < 0) return null;

  const stopPrice = dir === "LONG" ? rangeLow : rangeHigh;
  const risk = Math.abs(entryPrice - stopPrice);
  if (risk <= 0) return null;
  const targetPrice = dir === "LONG" ? entryPrice + CFG.TARGET_R * risk : entryPrice - CFG.TARGET_R * risk;

  let exitPrice = bars[bars.length - 1].c, exitType = "eod", exitBarMin = minuteET(bars[bars.length - 1]);
  for (let i = entryBar + 1; i < bars.length; i++) {
    const b = bars[i];
    if (dir === "LONG") {
      if (b.l <= stopPrice) { exitPrice = stopPrice; exitType = "stop"; exitBarMin = minuteET(b); break; }
      if (b.h >= targetPrice) { exitPrice = targetPrice; exitType = "target"; exitBarMin = minuteET(b); break; }
    } else {
      if (b.h >= stopPrice) { exitPrice = stopPrice; exitType = "stop"; exitBarMin = minuteET(b); break; }
      if (b.l <= targetPrice) { exitPrice = targetPrice; exitType = "target"; exitBarMin = minuteET(b); break; }
    }
  }
  const pnl = dir === "LONG" ? exitPrice - entryPrice : entryPrice - exitPrice;
  return {
    ticker, direction: dir, entryBarMin: minuteET(bars[entryBar]),
    entryPrice, stopPrice, targetPrice, risk,
    exitPrice, exitType, exitBarMin, r: pnl / risk,
  };
}

function fmtTime(m: number): string {
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`;
}

async function main() {
  console.log(`REPLAY ${DATE} — engine rules, ${CFG.TICKERS.length}-ticker universe\n`);
  const sims: Sim[] = [];
  for (const t of CFG.TICKERS) {
    const bars = await fetchDay(t);
    const s = simulate(t, bars);
    if (s) sims.push(s);
    else console.log(`  ${t.padEnd(6)} no signal (no clean range/gate/breakout)`);
  }

  // Engine takes signals chronologically, max 4 concurrent, DLL -4R on realized
  sims.sort((a, b) => a.entryBarMin - b.entryBarMin);
  const taken: Sim[] = [];
  let realized = 0;
  for (const s of sims) {
    const concurrent = taken.filter(t => t.entryBarMin <= s.entryBarMin && t.exitBarMin > s.entryBarMin).length;
    if (concurrent >= CFG.MAX_CONCURRENT) { console.log(`  ${s.ticker.padEnd(6)} SKIPPED (4 concurrent)`); continue; }
    const realizedAtEntry = taken.filter(t => t.exitBarMin <= s.entryBarMin).reduce((x, t) => x + t.r, 0);
    if (realizedAtEntry <= -CFG.DAILY_LOSS_LIMIT_R) { console.log(`  ${s.ticker.padEnd(6)} SKIPPED (daily loss limit)`); continue; }
    taken.push(s);
  }

  console.log("");
  for (const s of taken) {
    console.log(`  ${fmtTime(s.entryBarMin)}  ${s.ticker.padEnd(6)} ${s.direction.padEnd(6)} $${s.entryPrice.toFixed(2)} → $${s.exitPrice.toFixed(2)}  ${(s.r >= 0 ? "+" : "")}${s.r.toFixed(2)}R  (${s.exitType} @ ${fmtTime(s.exitBarMin)})`);
    realized += s.r;
  }
  console.log(`\n  DAY TOTAL: ${realized >= 0 ? "+" : ""}${realized.toFixed(2)}R (${taken.length} trades)`);
  console.log(`  At 1% risk on $95,896 equity: ${realized >= 0 ? "+" : "-"}$${Math.abs(realized * 958.96).toFixed(0)}`);
}

main().catch(console.error);
