/**
 * Crypto Research Backtest — Zarattini Method adapted for 24/7 crypto
 *
 * Adaptations from stock version:
 *  - Crypto API endpoint
 *  - "EOD" = 8 hours after entry (since crypto trades 24/7)
 *  - Daily session = ETH 9:30 AM ET as reference start
 *  - ETH/USD, SOL/USD, BTC/USD universe
 */

import { ALPACA_REST_URL } from "@/lib/constants";
import { calcATR } from "@/lib/indicators";
import type { AlpacaBar, Direction } from "@/lib/types";

const BT_TICKERS = ["ETH/USD", "SOL/USD", "BTC/USD"];
const BT_SHORT: Record<string, string> = {
  "ETH/USD": "ETH", "SOL/USD": "SOL", "BTC/USD": "BTC",
};
const START_DATE = "2025-06-09";
const END_DATE = "2026-06-09";
const CONTEXT_START = "2025-04-01";
const ORB_MINUTES = 5;
const SESSION_TIMEOUT_HOURS = 8; // crypto "EOD" substitute

function headers() {
  return {
    "APCA-API-KEY-ID": process.env.ALPACA_API_KEY!,
    "APCA-API-SECRET-KEY": process.env.ALPACA_API_SECRET!,
  };
}

async function fetchCryptoBars(symbol: string, timeframe: string, start: string, end: string): Promise<AlpacaBar[]> {
  const all: AlpacaBar[] = [];
  let pageToken: string | null = null;
  do {
    const params = new URLSearchParams({
      symbols: symbol, timeframe, start, end, limit: "10000", sort: "asc",
    });
    if (pageToken) params.set("page_token", pageToken);
    const res = await fetch(`${ALPACA_REST_URL}/v1beta3/crypto/us/bars?${params}`, { headers: headers() });
    if (!res.ok) { console.error(`[${symbol}] ${res.status}`); return []; }
    const data = await res.json();
    const bars: AlpacaBar[] = data.bars?.[symbol] ?? [];
    all.push(...bars);
    pageToken = data.next_page_token ?? null;
    if (pageToken) await new Promise(r => setTimeout(r, 200));
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

function barET(bar: AlpacaBar): { h: number; m: number } {
  const d = new Date(bar.t);
  const off = etOffset(d);
  return { h: d.getUTCHours() - off, m: d.getUTCMinutes() };
}

// Crypto "session" = bars within 9:30 AM - 11:30 AM ET window for ORB build
function isSessionStart(bar: AlpacaBar): boolean {
  const et = barET(bar);
  return et.h === 9 && et.m >= 30;
}

function barDateET(bar: AlpacaBar): string {
  const d = new Date(bar.t);
  const off = etOffset(d);
  const et = new Date(d.getTime() - off * 3600000);
  return et.toISOString().split("T")[0];
}

function getTradingDays(start: string, end: string): string[] {
  const days: string[] = [];
  const d = new Date(start + "T12:00:00Z");
  const endD = new Date(end + "T12:00:00Z");
  while (d <= endD) {
    if (d.getUTCDay() >= 1 && d.getUTCDay() <= 5) days.push(d.toISOString().split("T")[0]);
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return days;
}

interface Trade {
  date: string; ticker: string; direction: Direction;
  entryPrice: number; stopPrice: number; risk: number;
  exitPrice: number; exitType: string;
  rMultiple: number; barsHeld: number;
}

interface ResearchConfig {
  name: string;
  targetMultiplier: number;
  holdToTimeout: boolean;
  useBreakeven: boolean;
  partialTakeProfit: boolean;
  requireVWAPAlign: boolean;
  requireStrongClose: boolean;
  tickerFilter: Set<string> | null;
  dirFilter: Set<string> | null;
  maxTradesPerDay: number;
  dailyLossLimitR: number;
  timeoutHours: number;
}

const DEFAULT_CFG: ResearchConfig = {
  name: "default",
  targetMultiplier: 3,
  holdToTimeout: true,
  useBreakeven: false,
  partialTakeProfit: false,
  requireVWAPAlign: false,
  requireStrongClose: false,
  tickerFilter: null,
  dirFilter: null,
  maxTradesPerDay: 0,
  dailyLossLimitR: 0,
  timeoutHours: SESSION_TIMEOUT_HOURS,
};

interface DayContext {
  ticker: string;
  atr14: number;
}

function computeContext(ticker: string, dailyBars: AlpacaBar[], dayIdx: number): DayContext | null {
  if (dayIdx < 15) return null;
  const prior = dailyBars.slice(Math.max(0, dayIdx - 20), dayIdx);
  if (prior.length < 15) return null;
  const hlc = prior.map(b => ({ high: b.h, low: b.l, close: b.c }));
  const atr14 = calcATR(hlc, 14);
  if (atr14 <= 0) return null;
  return { ticker, atr14 };
}

function simulateDay(
  date: string,
  contexts: DayContext[],
  intradayByTicker: Map<string, AlpacaBar[]>,
  cfg: ResearchConfig,
): Trade[] {
  const trades: Trade[] = [];
  let dayR = 0;
  let dayTrades = 0;

  for (const ctx of contexts) {
    if (cfg.dailyLossLimitR > 0 && dayR <= -cfg.dailyLossLimitR) break;
    if (cfg.maxTradesPerDay > 0 && dayTrades >= cfg.maxTradesPerDay) break;
    if (cfg.tickerFilter && !cfg.tickerFilter.has(ctx.ticker)) continue;

    const bars = intradayByTicker.get(ctx.ticker);
    if (!bars || bars.length < ORB_MINUTES + 10) continue;

    // Find session start (9:30 AM ET) bar
    const sessionStartIdx = bars.findIndex(b => isSessionStart(b));
    if (sessionStartIdx < 0 || sessionStartIdx + ORB_MINUTES + 30 > bars.length) continue;

    // Build opening range from first 5 bars after 9:30
    const rb = bars.slice(sessionStartIdx, sessionStartIdx + ORB_MINUTES);
    const rangeHigh = Math.max(...rb.map(b => b.h));
    const rangeLow = Math.min(...rb.map(b => b.l));
    const rangeWidth = rangeHigh - rangeLow;
    if (rangeWidth <= 0) continue;

    const firstOpen = rb[0].o;
    const firstClose = rb[rb.length - 1].c;
    if (Math.abs(firstClose - firstOpen) < rangeWidth * 0.1) continue;
    const candleDir: Direction = firstClose > firstOpen ? "LONG" : "SHORT";

    if (cfg.dirFilter && !cfg.dirFilter.has(`${BT_SHORT[ctx.ticker]} ${candleDir}`)) continue;

    // VWAP tracking from session start
    let vp = 0, vol = 0;
    for (const b of rb) { vp += ((b.h + b.l + b.c) / 3) * b.v; vol += b.v; }

    // Wait for breakout
    let entryBar = -1;
    let entryPrice = 0;
    const breakoutWindow = Math.min(sessionStartIdx + 60, bars.length);

    for (let i = sessionStartIdx + ORB_MINUTES; i < breakoutWindow; i++) {
      const b = bars[i];
      vp += ((b.h + b.l + b.c) / 3) * b.v;
      vol += b.v;

      if (candleDir === "LONG" && b.c > rangeHigh) {
        if (cfg.requireStrongClose) {
          const barRange = b.h - b.l;
          if (barRange > 0 && (b.c - b.l) / barRange < 0.7) continue;
        }
        entryBar = i;
        entryPrice = b.c;
        break;
      }
      if (candleDir === "SHORT" && b.c < rangeLow) {
        if (cfg.requireStrongClose) {
          const barRange = b.h - b.l;
          if (barRange > 0 && (b.h - b.c) / barRange < 0.7) continue;
        }
        entryBar = i;
        entryPrice = b.c;
        break;
      }
    }

    if (entryBar < 0) continue;

    const vwap = vol > 0 ? vp / vol : 0;
    if (cfg.requireVWAPAlign) {
      const aligned = candleDir === "LONG" ? entryPrice >= vwap : entryPrice <= vwap;
      if (!aligned) continue;
    }

    const stopPrice = candleDir === "LONG" ? rangeLow : rangeHigh;
    const risk = candleDir === "LONG" ? entryPrice - stopPrice : stopPrice - entryPrice;
    if (risk <= 0) continue;

    const targetPrice = candleDir === "LONG"
      ? entryPrice + cfg.targetMultiplier * risk
      : entryPrice - cfg.targetMultiplier * risk;

    // Simulate to stop, target, or timeout
    const timeoutBars = cfg.timeoutHours * 60; // minutes
    const maxExitBar = Math.min(entryBar + timeoutBars, bars.length - 1);

    let exitPrice = 0;
    let exitType = "timeout";
    let curStop = stopPrice;
    let bestReachedR = 0;
    let exitBar = maxExitBar;
    let partialTaken = false;
    let partialR = 0;

    for (let i = entryBar + 1; i <= maxExitBar; i++) {
      const b = bars[i];
      const unrealized = candleDir === "LONG"
        ? (b.h - entryPrice) / risk
        : (entryPrice - b.l) / risk;
      bestReachedR = Math.max(bestReachedR, unrealized);

      if (cfg.partialTakeProfit && !partialTaken && bestReachedR >= 1.0) {
        partialTaken = true;
        partialR = 0.5;
        curStop = entryPrice;
      }
      if (cfg.useBreakeven && bestReachedR >= 0.15) curStop = entryPrice;

      if (candleDir === "LONG") {
        if (b.l <= curStop) { exitPrice = curStop; exitType = curStop === entryPrice ? "be" : "stop"; exitBar = i; break; }
        if (b.h >= targetPrice) { exitPrice = targetPrice; exitType = "target"; exitBar = i; break; }
      } else {
        if (b.h >= curStop) { exitPrice = curStop; exitType = curStop === entryPrice ? "be" : "stop"; exitBar = i; break; }
        if (b.l <= targetPrice) { exitPrice = targetPrice; exitType = "target"; exitBar = i; break; }
      }
    }

    if (exitPrice === 0) {
      exitPrice = bars[maxExitBar].c;
      exitType = "timeout";
    }

    const pnl = candleDir === "LONG" ? exitPrice - entryPrice : entryPrice - exitPrice;
    const remainderR = pnl / risk;
    const rMul = cfg.partialTakeProfit && partialTaken
      ? partialR + 0.5 * remainderR
      : remainderR;

    trades.push({
      date, ticker: BT_SHORT[ctx.ticker], direction: candleDir,
      entryPrice, stopPrice, risk,
      exitPrice, exitType, rMultiple: rMul,
      barsHeld: exitBar - entryBar,
    });
    dayR += rMul;
    dayTrades++;
  }
  return trades;
}

function compoundEquity(trades: Trade[], startCapital: number, riskPct: number) {
  const sorted = [...trades].sort((a, b) => a.date.localeCompare(b.date));
  let equity = startCapital, peak = startCapital, maxDD = 0;
  for (const t of sorted) {
    const pnl = (equity * riskPct) * t.rMultiple;
    equity += pnl;
    if (equity > peak) peak = equity;
    const dd = peak - equity;
    if (dd > maxDD) maxDD = dd;
  }
  return { endEquity: equity, maxDDDollars: maxDD };
}

function fmt$(n: number): string {
  const s = n >= 0 ? "+" : "-";
  return s + "$" + Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function reportConfig(cfg: ResearchConfig, trades: Trade[]) {
  const W = trades.filter(t => t.rMultiple > 0.2);
  const L = trades.filter(t => t.rMultiple < -0.2);
  const totalR = trades.reduce((s, t) => s + t.rMultiple, 0);
  const winRate = trades.length > 0 ? (W.length / trades.length) * 100 : 0;
  const grossWin = W.reduce((s, t) => s + t.rMultiple, 0);
  const grossLoss = Math.abs(L.reduce((s, t) => s + t.rMultiple, 0));
  const pf = grossLoss > 0 ? grossWin / grossLoss : 0;
  const avgWinR = W.length > 0 ? grossWin / W.length : 0;
  const avgLossR = L.length > 0 ? -grossLoss / L.length : 0;

  const r1 = compoundEquity(trades, 100_000, 0.01);
  console.log(`  ${cfg.name.padEnd(28)} ${String(trades.length).padEnd(5)} ${(winRate.toFixed(0) + "%").padEnd(5)} ${("+" + avgWinR.toFixed(2)).padEnd(7)} ${(avgLossR.toFixed(2)).padEnd(7)} ${((totalR >= 0 ? "+" : "") + totalR.toFixed(2) + "R").padEnd(9)} ${(pf.toFixed(2) + "x").padEnd(6)} ${fmt$(r1.endEquity - 100_000).padEnd(11)} -$${r1.maxDDDollars.toLocaleString("en-US", { maximumFractionDigits: 0 })}`);
}

const CONFIGS: ResearchConfig[] = [
  // Baselines
  { ...DEFAULT_CFG, name: "BASELINE: 3R+8hr", targetMultiplier: 3 },
  { ...DEFAULT_CFG, name: "5R+8hr", targetMultiplier: 5 },
  { ...DEFAULT_CFG, name: "10R+8hr (Zarattini)", targetMultiplier: 10 },
  { ...DEFAULT_CFG, name: "1R+8hr", targetMultiplier: 1 },

  // Hold longer
  { ...DEFAULT_CFG, name: "3R+12hr", targetMultiplier: 3, timeoutHours: 12 },
  { ...DEFAULT_CFG, name: "3R+24hr", targetMultiplier: 3, timeoutHours: 24 },
  { ...DEFAULT_CFG, name: "10R+24hr", targetMultiplier: 10, timeoutHours: 24 },

  // Ticker filters
  { ...DEFAULT_CFG, name: "3R ETH+SOL only", targetMultiplier: 3, tickerFilter: new Set(["ETH/USD", "SOL/USD"]) },
  { ...DEFAULT_CFG, name: "10R ETH+SOL only", targetMultiplier: 10, tickerFilter: new Set(["ETH/USD", "SOL/USD"]) },
  { ...DEFAULT_CFG, name: "3R ETH only", targetMultiplier: 3, tickerFilter: new Set(["ETH/USD"]) },
  { ...DEFAULT_CFG, name: "3R BTC only", targetMultiplier: 3, tickerFilter: new Set(["BTC/USD"]) },

  // Direction × ticker (from prior crypto analysis: ETH LONG + SOL SHORT were winners)
  { ...DEFAULT_CFG, name: "3R ETH-L+SOL-S", targetMultiplier: 3, dirFilter: new Set(["ETH LONG", "SOL SHORT"]) },
  { ...DEFAULT_CFG, name: "10R ETH-L+SOL-S", targetMultiplier: 10, dirFilter: new Set(["ETH LONG", "SOL SHORT"]) },

  // VWAP align
  { ...DEFAULT_CFG, name: "3R+VWAP", targetMultiplier: 3, requireVWAPAlign: true },
  { ...DEFAULT_CFG, name: "10R+VWAP", targetMultiplier: 10, requireVWAPAlign: true },

  // Risk management
  { ...DEFAULT_CFG, name: "3R+DLL3", targetMultiplier: 3, dailyLossLimitR: 3 },
  { ...DEFAULT_CFG, name: "3R+max2/day", targetMultiplier: 3, maxTradesPerDay: 2 },

  // Partial profit
  { ...DEFAULT_CFG, name: "3R+partial@1R", targetMultiplier: 3, partialTakeProfit: true },
  { ...DEFAULT_CFG, name: "5R+partial@1R", targetMultiplier: 5, partialTakeProfit: true },

  // Combos
  { ...DEFAULT_CFG, name: "3R ETH+SOL+24hr", targetMultiplier: 3, tickerFilter: new Set(["ETH/USD", "SOL/USD"]), timeoutHours: 24 },
  { ...DEFAULT_CFG, name: "3R ETH-L+SOL-S+24hr", targetMultiplier: 3, dirFilter: new Set(["ETH LONG", "SOL SHORT"]), timeoutHours: 24 },
  { ...DEFAULT_CFG, name: "3R ULTIMATE", targetMultiplier: 3, dirFilter: new Set(["ETH LONG", "SOL SHORT"]), timeoutHours: 24, partialTakeProfit: true, dailyLossLimitR: 3 },
];

async function main() {
  if (!process.env.ALPACA_API_KEY) throw new Error("Set ALPACA_API_KEY");

  console.log("[crypto-research] ORB Crypto Research Backtest");
  console.log(`[crypto-research] Period: ${START_DATE} → ${END_DATE}`);
  console.log(`[crypto-research] Tickers: ${BT_TICKERS.join(", ")}`);
  console.log(`[crypto-research] ORB: ${ORB_MINUTES}-min, default timeout: ${SESSION_TIMEOUT_HOURS}h\n`);

  console.log("[crypto-research] Fetching daily bars...");
  const dailyByTicker = new Map<string, AlpacaBar[]>();
  for (const ticker of BT_TICKERS) {
    const bars = await fetchCryptoBars(ticker, "1Day", CONTEXT_START, END_DATE);
    dailyByTicker.set(ticker, bars);
    console.log(`  ${BT_SHORT[ticker]}... ${bars.length} bars`);
  }

  console.log("[crypto-research] Fetching 1-min intraday bars (this takes a moment)...");
  const allMinBars = new Map<string, AlpacaBar[]>();
  for (const ticker of BT_TICKERS) {
    const bars = await fetchCryptoBars(ticker, "1Min", START_DATE + "T00:00:00Z", END_DATE + "T23:59:59Z");
    allMinBars.set(ticker, bars);
    console.log(`  ${BT_SHORT[ticker]}... ${bars.length} bars`);
  }

  // Group by date (using 9:30 AM ET as session start)
  console.log("[crypto-research] Processing intraday data...");
  const dayBarsMap = new Map<string, Map<string, AlpacaBar[]>>();
  for (const [ticker, bars] of allMinBars) {
    for (const bar of bars) {
      const date = barDateET(bar);
      if (!dayBarsMap.has(date)) dayBarsMap.set(date, new Map());
      const dm = dayBarsMap.get(date)!;
      if (!dm.has(ticker)) dm.set(ticker, []);
      dm.get(ticker)!.push(bar);
    }
  }

  const dailyDateIdx = new Map<string, Map<string, number>>();
  for (const [ticker, bars] of dailyByTicker) {
    for (let i = 0; i < bars.length; i++) {
      const d = bars[i].t.split("T")[0];
      if (!dailyDateIdx.has(d)) dailyDateIdx.set(d, new Map());
      dailyDateIdx.get(d)!.set(ticker, i);
    }
  }

  const tradingDays = getTradingDays(START_DATE, END_DATE);

  interface DayData { contexts: DayContext[]; intradayByTicker: Map<string, AlpacaBar[]>; }
  const dayDataMap = new Map<string, DayData>();

  for (const date of tradingDays) {
    const dayBars = dayBarsMap.get(date);
    if (!dayBars) continue;
    const contexts: DayContext[] = [];
    const intradayByTicker = new Map<string, AlpacaBar[]>();

    for (const ticker of BT_TICKERS) {
      const bars = dayBars.get(ticker);
      if (!bars || bars.length < 60) continue;
      const dailyIdx = dailyDateIdx.get(date)?.get(ticker);
      const daily = dailyByTicker.get(ticker);
      if (dailyIdx === undefined || !daily) continue;
      const ctx = computeContext(ticker, daily, dailyIdx);
      if (!ctx) continue;
      contexts.push(ctx);
      intradayByTicker.set(ticker, bars);
    }
    if (contexts.length > 0) dayDataMap.set(date, { contexts, intradayByTicker });
  }

  console.log(`[crypto-research] ${dayDataMap.size} tradable days precomputed.\n`);

  console.log("╔══════════════════════════════════════════════════════════════════════════════════════════╗");
  console.log("║       CRYPTO ZARATTINI-STYLE ORB — 8hr+ Hold with Large R Targets                       ║");
  console.log("╚══════════════════════════════════════════════════════════════════════════════════════════╝");
  console.log("\n  Position size: 1% equity (compounded) | Starting capital: $100,000\n");
  console.log(`  ${"CONFIG".padEnd(28)} ${"#".padEnd(5)} ${"WIN%".padEnd(5)} ${"AVG+".padEnd(7)} ${"AVG-".padEnd(7)} ${"TOTAL R".padEnd(9)} ${"PF".padEnd(6)} ${"P&L 1%".padEnd(11)} MaxDD`);
  console.log("  " + "─".repeat(95));

  let bestR = -Infinity, bestCfg = "";
  const allResults: { cfg: ResearchConfig; trades: Trade[]; totalR: number }[] = [];

  for (const cfg of CONFIGS) {
    const trades: Trade[] = [];
    for (const [date, dd] of dayDataMap) {
      trades.push(...simulateDay(date, dd.contexts, dd.intradayByTicker, cfg));
    }
    reportConfig(cfg, trades);
    const totalR = trades.reduce((s, t) => s + t.rMultiple, 0);
    allResults.push({ cfg, trades, totalR });
    if (totalR > bestR) { bestR = totalR; bestCfg = cfg.name; }
  }

  console.log("  " + "─".repeat(95));
  console.log(`  BEST: ${bestCfg} → ${bestR >= 0 ? "+" : ""}${bestR.toFixed(2)}R\n`);

  const best = allResults.find(r => r.cfg.name === bestCfg)!;

  console.log("\n── BEST: Per-ticker × direction ──");
  for (const ticker of BT_TICKERS) {
    const sh = BT_SHORT[ticker];
    for (const dir of ["LONG", "SHORT"] as const) {
      const tt = best.trades.filter(t => t.ticker === sh && t.direction === dir);
      if (tt.length === 0) continue;
      const tw = tt.filter(t => t.rMultiple > 0.2).length;
      const tr = tt.reduce((s, t) => s + t.rMultiple, 0);
      console.log(`  ${(sh + " " + dir).padEnd(15)} ${String(tt.length).padEnd(5)} ${(((tw / tt.length) * 100).toFixed(1) + "%").padEnd(8)} ${(tr >= 0 ? "+" : "") + tr.toFixed(2)}R`);
    }
  }

  console.log("\n── EXIT TYPE BREAKDOWN ──");
  const exitTypes = new Map<string, { count: number; totalR: number }>();
  for (const t of best.trades) {
    if (!exitTypes.has(t.exitType)) exitTypes.set(t.exitType, { count: 0, totalR: 0 });
    const e = exitTypes.get(t.exitType)!;
    e.count++; e.totalR += t.rMultiple;
  }
  for (const [type, data] of exitTypes) {
    console.log(`  ${type.padEnd(10)} ${String(data.count).padEnd(5)} avg ${(data.totalR / data.count >= 0 ? "+" : "") + (data.totalR / data.count).toFixed(2)}R  total ${(data.totalR >= 0 ? "+" : "") + data.totalR.toFixed(2)}R`);
  }
}

main().catch(console.error);
