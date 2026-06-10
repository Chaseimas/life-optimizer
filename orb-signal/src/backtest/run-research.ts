/**
 * Research-Based ORB Backtest — Zarattini Method
 *
 * Based on:
 *  - Zarattini & Aziz "Can Day Trading Really Be Profitable?" (2023)
 *  - "A Profitable Day Trading Strategy" Zarattini, Barbon, Aziz (2024)
 *
 * Key differences from our current approach:
 *  1. 5-min ORB (smaller range, more breakouts)
 *  2. Target = 10R (not 1R) — the BIG change
 *  3. Hold to EOD if no stop/target — let winners run
 *  4. NO breakeven stop — original stop only
 *  5. NO failure exit, NO EMA trail
 *  6. Stocks in Play filter (RVOL > 1.0)
 *  7. NR7 filter — prior day narrowest range of last 7 days (Crabel)
 *  8. VWAP slope alignment
 *
 * Position sizing: 1% account risk / stop distance
 */

import { ALPACA_REST_URL } from "@/lib/constants";
import { calcSMA, calcATR } from "@/lib/indicators";
import type { AlpacaBar, Direction } from "@/lib/types";

const BT_TICKERS = ["SPY", "QQQ", "AAPL", "TSLA", "NVDA", "AMD"];
const START_DATE = "2025-06-09";  // 1 year
const END_DATE = "2026-06-09";
const CONTEXT_START = "2025-04-01";
const ORB_MINUTES = 5; // Zarattini's recommended

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

function isMarketHours(bar: AlpacaBar): boolean {
  const et = barET(bar);
  if (et.h < 9 || et.h >= 16) return false;
  if (et.h === 9 && et.m < 30) return false;
  return true;
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
  rvol: number; isNR7: boolean; vwapAligned: boolean;
}

interface ResearchConfig {
  name: string;
  targetMultiplier: number;  // X * risk, e.g. 10 for 10R target
  holdToEOD: boolean;        // if no target/stop, hold to close
  useBreakeven: boolean;     // move stop to entry at 0.15R
  rvolThreshold: number;     // minimum relative volume (1.0 = baseline)
  requireNR7: boolean;       // prior day narrowest range of last 7
  requireVWAPAlign: boolean; // VWAP slope must align with direction
  requireStrongClose: boolean; // close in top/bottom 30% of breakout bar
  tickerFilter: Set<string> | null;
  dirFilter: Set<string> | null;  // "TICKER DIR" subset
  maxTradesPerDay: number;        // 0 = no limit
  dailyLossLimitR: number;        // 0 = no limit, e.g. 3 = stop trading day after -3R
  partialTakeProfit: boolean;     // take 50% off at 1R, let rest run
}

const DEFAULT_CFG: ResearchConfig = {
  name: "default",
  targetMultiplier: 3,
  holdToEOD: true,
  useBreakeven: false,
  rvolThreshold: 1.0,
  requireNR7: false,
  requireVWAPAlign: false,
  requireStrongClose: false,
  tickerFilter: null,
  dirFilter: null,
  maxTradesPerDay: 0,
  dailyLossLimitR: 0,
  partialTakeProfit: false,
};

interface DayContext {
  ticker: string;
  atr14: number;
  prior7Ranges: number[];
  priorDayRange: number;
  isNR7: boolean;
}

function computeContext(ticker: string, dailyBars: AlpacaBar[], dayIdx: number): DayContext | null {
  if (dayIdx < 15) return null;
  const prior = dailyBars.slice(Math.max(0, dayIdx - 20), dayIdx);
  if (prior.length < 15) return null;

  const hlc = prior.map(b => ({ high: b.h, low: b.l, close: b.c }));
  const atr14 = calcATR(hlc, 14);
  if (atr14 <= 0) return null;

  // NR7 = prior day's range is narrowest of last 7 days
  const last7 = prior.slice(-7);
  const ranges = last7.map(b => b.h - b.l);
  const priorDayRange = ranges[ranges.length - 1];
  const isNR7 = ranges.every(r => r >= priorDayRange);

  return { ticker, atr14, prior7Ranges: ranges, priorDayRange, isNR7 };
}

function simulateDay(
  date: string,
  contexts: DayContext[],
  intradayByTicker: Map<string, AlpacaBar[]>,
  rvolByTicker: Map<string, number>,
  cfg: ResearchConfig,
): Trade[] {
  const trades: Trade[] = [];
  let dayR = 0;          // cumulative R for the day
  let dayTrades = 0;     // trades taken today

  for (const ctx of contexts) {
    // Daily loss limit
    if (cfg.dailyLossLimitR > 0 && dayR <= -cfg.dailyLossLimitR) break;
    // Max trades per day
    if (cfg.maxTradesPerDay > 0 && dayTrades >= cfg.maxTradesPerDay) break;
    if (cfg.tickerFilter && !cfg.tickerFilter.has(ctx.ticker)) continue;
    if (cfg.requireNR7 && !ctx.isNR7) continue;

    const bars = intradayByTicker.get(ctx.ticker);
    if (!bars || bars.length < ORB_MINUTES + 10) continue;

    const rvol = rvolByTicker.get(ctx.ticker) ?? 0;
    if (rvol < cfg.rvolThreshold) continue;

    // Build opening range from first 5 bars
    const rb = bars.slice(0, ORB_MINUTES);
    const rangeHigh = Math.max(...rb.map(b => b.h));
    const rangeLow = Math.min(...rb.map(b => b.l));
    const rangeWidth = rangeHigh - rangeLow;
    if (rangeWidth <= 0) continue;

    // Determine direction by first 5-min candle (Zarattini's rule)
    const firstOpen = rb[0].o;
    const firstClose = rb[rb.length - 1].c;
    if (Math.abs(firstClose - firstOpen) < rangeWidth * 0.1) continue; // skip doji
    const candleDir: Direction = firstClose > firstOpen ? "LONG" : "SHORT";

    // Build cumulative VWAP from opening range
    let vp = 0, vol = 0;
    for (const b of rb) { vp += ((b.h + b.l + b.c) / 3) * b.v; vol += b.v; }
    const vwapAtOpen = vol > 0 ? vp / vol : 0;

    // Wait for breakout entry: candle CLOSE outside range, in direction of opening bar
    let entryBar = -1;
    let entryPrice = 0;
    let breakoutBarObj: AlpacaBar | null = null;

    for (let i = ORB_MINUTES; i < Math.min(bars.length, 60); i++) {
      const b = bars[i];
      vp += ((b.h + b.l + b.c) / 3) * b.v;
      vol += b.v;

      if (candleDir === "LONG" && b.c > rangeHigh) {
        // Strong close check
        if (cfg.requireStrongClose) {
          const barRange = b.h - b.l;
          if (barRange > 0 && (b.c - b.l) / barRange < 0.7) continue;
        }
        entryBar = i;
        entryPrice = b.c;
        breakoutBarObj = b;
        break;
      }
      if (candleDir === "SHORT" && b.c < rangeLow) {
        if (cfg.requireStrongClose) {
          const barRange = b.h - b.l;
          if (barRange > 0 && (b.h - b.c) / barRange < 0.7) continue;
        }
        entryBar = i;
        entryPrice = b.c;
        breakoutBarObj = b;
        break;
      }
    }

    if (entryBar < 0 || !breakoutBarObj) continue;

    // VWAP alignment check
    const vwap = vol > 0 ? vp / vol : 0;
    const vwapAligned = candleDir === "LONG" ? entryPrice >= vwap : entryPrice <= vwap;
    if (cfg.requireVWAPAlign && !vwapAligned) continue;

    // Direction × ticker filter
    if (cfg.dirFilter && !cfg.dirFilter.has(`${ctx.ticker} ${candleDir}`)) continue;

    // Stop = opposite end of 5-min ORB range
    const stopPrice = candleDir === "LONG" ? rangeLow : rangeHigh;
    const risk = candleDir === "LONG" ? entryPrice - stopPrice : stopPrice - entryPrice;
    if (risk <= 0) continue;

    // Target = entry +/- (cfg.targetMultiplier * risk)
    const targetPrice = candleDir === "LONG"
      ? entryPrice + cfg.targetMultiplier * risk
      : entryPrice - cfg.targetMultiplier * risk;

    // Simulate until stop, target, or EOD
    // Partial profit: 50% off at +1R, then BE stop, rest runs to target/EOD
    let exitPrice = 0;
    let exitType = "eod";
    let curStop = stopPrice;
    let bestReachedR = 0;
    let exitBar = bars.length - 1;
    let partialTaken = false;
    let partialR = 0; // R captured from 50% at 1R

    for (let i = entryBar + 1; i < bars.length; i++) {
      const b = bars[i];

      // Track best R
      const unrealized = candleDir === "LONG"
        ? (b.h - entryPrice) / risk
        : (entryPrice - b.l) / risk;
      bestReachedR = Math.max(bestReachedR, unrealized);

      // Partial profit at 1R (move 50%, lock breakeven on rest)
      if (cfg.partialTakeProfit && !partialTaken && bestReachedR >= 1.0) {
        partialTaken = true;
        partialR = 0.5; // 50% size × 1R = 0.5R locked
        curStop = entryPrice; // breakeven on remainder
      }

      // Breakeven stop activation
      if (cfg.useBreakeven && bestReachedR >= 0.15) {
        curStop = entryPrice;
      }

      if (candleDir === "LONG") {
        if (b.l <= curStop) { exitPrice = curStop; exitType = curStop === entryPrice ? "be" : "stop"; exitBar = i; break; }
        if (b.h >= targetPrice) { exitPrice = targetPrice; exitType = "target"; exitBar = i; break; }
      } else {
        if (b.h >= curStop) { exitPrice = curStop; exitType = curStop === entryPrice ? "be" : "stop"; exitBar = i; break; }
        if (b.l <= targetPrice) { exitPrice = targetPrice; exitType = "target"; exitBar = i; break; }
      }
    }

    // If still in trade, exit at last bar (EOD)
    if (exitPrice === 0) {
      exitPrice = bars[bars.length - 1].c;
      exitType = "eod";
      exitBar = bars.length - 1;
    }

    const pnl = candleDir === "LONG" ? exitPrice - entryPrice : entryPrice - exitPrice;
    // If partial taken, only 50% of size rides remaining
    const remainderR = pnl / risk;
    const rMul = cfg.partialTakeProfit && partialTaken
      ? partialR + 0.5 * remainderR
      : remainderR;

    trades.push({
      date, ticker: ctx.ticker, direction: candleDir,
      entryPrice, stopPrice, risk,
      exitPrice, exitType, rMultiple: rMul,
      barsHeld: exitBar - entryBar,
      rvol, isNR7: ctx.isNR7, vwapAligned,
    });
    dayR += rMul;
    dayTrades++;
  }

  return trades;
}

// ─── Equity & reporting ───
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

  const START = 100_000;
  const r1 = compoundEquity(trades, START, 0.01);

  console.log(`  ${cfg.name.padEnd(28)} ${String(trades.length).padEnd(5)} ${(winRate.toFixed(0) + "%").padEnd(5)} ${("+" + avgWinR.toFixed(2)).padEnd(7)} ${(avgLossR.toFixed(2)).padEnd(7)} ${((totalR >= 0 ? "+" : "") + totalR.toFixed(2) + "R").padEnd(9)} ${(pf.toFixed(2) + "x").padEnd(6)} ${fmt$(r1.endEquity - START).padEnd(11)} -$${r1.maxDDDollars.toLocaleString("en-US", { maximumFractionDigits: 0 })}`);
}

// Winning combos identified from prior run (3R+EOD, per-ticker breakdown):
// SPY LONG +16R, QQQ SHORT +15R, QQQ LONG +13R, AMD LONG +12R, TSLA L/S ~+6.5R, SPY SHORT +4R, AMD SHORT +1.5R, NVDA LONG +1R
// LOSERS: AAPL LONG -6.5R, AAPL SHORT -1.3R, NVDA SHORT -10.9R
const WINNERS_ONLY = new Set([
  "SPY LONG", "SPY SHORT", "QQQ LONG", "QQQ SHORT",
  "AMD LONG", "AMD SHORT", "TSLA LONG", "TSLA SHORT", "NVDA LONG"
]);
const STRONG_WINNERS = new Set([
  "SPY LONG", "QQQ LONG", "QQQ SHORT", "AMD LONG", "TSLA LONG", "TSLA SHORT"
]);

const CONFIGS: ResearchConfig[] = [
  // ─── Baselines from prior run ───
  { ...DEFAULT_CFG, name: "BASELINE: 3R+EOD", targetMultiplier: 3 },
  { ...DEFAULT_CFG, name: "10R+EOD (Zarattini)", targetMultiplier: 10 },

  // ─── DRAWDOWN REDUCTION: filter losers ───
  { ...DEFAULT_CFG, name: "3R+EOD no losers", targetMultiplier: 3, dirFilter: WINNERS_ONLY },
  { ...DEFAULT_CFG, name: "10R+EOD no losers", targetMultiplier: 10, dirFilter: WINNERS_ONLY },
  { ...DEFAULT_CFG, name: "3R+EOD strong only", targetMultiplier: 3, dirFilter: STRONG_WINNERS },
  { ...DEFAULT_CFG, name: "10R+EOD strong only", targetMultiplier: 10, dirFilter: STRONG_WINNERS },

  // ─── Daily loss limit (stop trading after -3R day) ───
  { ...DEFAULT_CFG, name: "3R+EOD DLL=-3R", targetMultiplier: 3, dailyLossLimitR: 3 },
  { ...DEFAULT_CFG, name: "3R+EOD DLL=-2R", targetMultiplier: 3, dailyLossLimitR: 2 },
  { ...DEFAULT_CFG, name: "10R+EOD DLL=-3R", targetMultiplier: 10, dailyLossLimitR: 3 },

  // ─── Max trades per day ───
  { ...DEFAULT_CFG, name: "3R+EOD max2/day", targetMultiplier: 3, maxTradesPerDay: 2 },
  { ...DEFAULT_CFG, name: "3R+EOD max3/day", targetMultiplier: 3, maxTradesPerDay: 3 },

  // ─── Combos: winners only + DLL ───
  { ...DEFAULT_CFG, name: "3R+EOD winners+DLL3", targetMultiplier: 3, dirFilter: WINNERS_ONLY, dailyLossLimitR: 3 },
  { ...DEFAULT_CFG, name: "10R+EOD winners+DLL3", targetMultiplier: 10, dirFilter: WINNERS_ONLY, dailyLossLimitR: 3 },
  { ...DEFAULT_CFG, name: "3R+EOD strong+DLL2", targetMultiplier: 3, dirFilter: STRONG_WINNERS, dailyLossLimitR: 2 },
  { ...DEFAULT_CFG, name: "3R+EOD strong+max2", targetMultiplier: 3, dirFilter: STRONG_WINNERS, maxTradesPerDay: 2 },

  // ─── VWAP align + winners ───
  { ...DEFAULT_CFG, name: "3R+EOD VWAP+winners", targetMultiplier: 3, dirFilter: WINNERS_ONLY, requireVWAPAlign: true },
  { ...DEFAULT_CFG, name: "10R+EOD VWAP+winners", targetMultiplier: 10, dirFilter: WINNERS_ONLY, requireVWAPAlign: true },

  // ─── RVOL filter (Stocks in Play) ───
  { ...DEFAULT_CFG, name: "3R+EOD RVOL1.2 winners", targetMultiplier: 3, dirFilter: WINNERS_ONLY, rvolThreshold: 1.2 },
  { ...DEFAULT_CFG, name: "3R+EOD RVOL1.5 winners", targetMultiplier: 3, dirFilter: WINNERS_ONLY, rvolThreshold: 1.5 },

  // ─── PARTIAL PROFIT (50% off at 1R, rest holds to EOD) ───
  { ...DEFAULT_CFG, name: "3R+EOD partial@1R", targetMultiplier: 3, partialTakeProfit: true },
  { ...DEFAULT_CFG, name: "5R+EOD partial@1R", targetMultiplier: 5, partialTakeProfit: true },
  { ...DEFAULT_CFG, name: "3R partial winners", targetMultiplier: 3, dirFilter: WINNERS_ONLY, partialTakeProfit: true },

  // ─── KITCHEN SINK (all filters combined) ───
  { ...DEFAULT_CFG, name: "ULTIMATE: 3R winners+DLL+max+partial", targetMultiplier: 3, dirFilter: WINNERS_ONLY, dailyLossLimitR: 3, maxTradesPerDay: 3, partialTakeProfit: true },
  { ...DEFAULT_CFG, name: "ULTIMATE: 10R winners+DLL+partial", targetMultiplier: 10, dirFilter: WINNERS_ONLY, dailyLossLimitR: 3, partialTakeProfit: true },
];

async function main() {
  if (!process.env.ALPACA_API_KEY) throw new Error("Set ALPACA_API_KEY");

  console.log("[research] ORB Research-Based Backtest (Zarattini Method)");
  console.log(`[research] Period: ${START_DATE} → ${END_DATE}`);
  console.log(`[research] Tickers: ${BT_TICKERS.join(", ")}`);
  console.log(`[research] ORB: ${ORB_MINUTES}-minute opening range\n`);

  // Fetch daily bars
  console.log("[research] Fetching daily bars...");
  const dailyByTicker = new Map<string, AlpacaBar[]>();
  for (const ticker of BT_TICKERS) {
    const bars = await fetchStockBars(ticker, "1Day", CONTEXT_START, END_DATE);
    dailyByTicker.set(ticker, bars);
    console.log(`  ${ticker}... ${bars.length} bars`);
  }

  // Fetch 1-min bars
  console.log("[research] Fetching 1-min intraday bars...");
  const allMinBars = new Map<string, AlpacaBar[]>();
  for (const ticker of BT_TICKERS) {
    const bars = await fetchStockBars(ticker, "1Min", START_DATE, END_DATE);
    allMinBars.set(ticker, bars);
    console.log(`  ${ticker}... ${bars.length} bars`);
  }

  // Group intraday by date
  console.log("[research] Processing intraday data...");
  const dayBarsMap = new Map<string, Map<string, AlpacaBar[]>>();
  for (const [ticker, bars] of allMinBars) {
    for (const bar of bars) {
      if (!isMarketHours(bar)) continue;
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

  // Precompute day data with RVOL (today's first 5 min vs prior 14 days first 5 min)
  interface DayData { contexts: DayContext[]; intradayByTicker: Map<string, AlpacaBar[]>; rvolByTicker: Map<string, number>; }
  const dayDataMap = new Map<string, DayData>();

  // Track prior 14-day first-5-min volumes per ticker
  const priorVolsByTicker = new Map<string, number[]>();
  for (const ticker of BT_TICKERS) priorVolsByTicker.set(ticker, []);

  for (const date of tradingDays) {
    const dayBars = dayBarsMap.get(date);
    if (!dayBars) continue;

    const contexts: DayContext[] = [];
    const intradayByTicker = new Map<string, AlpacaBar[]>();
    const rvolByTicker = new Map<string, number>();

    for (const ticker of BT_TICKERS) {
      const bars = dayBars.get(ticker);
      if (!bars || bars.length < ORB_MINUTES + 5) continue;

      const dailyIdx = dailyDateIdx.get(date)?.get(ticker);
      const daily = dailyByTicker.get(ticker);
      if (dailyIdx === undefined || !daily) continue;

      const ctx = computeContext(ticker, daily, dailyIdx);
      if (!ctx) continue;

      // Calculate today's first 5-min volume
      const todayFirst5Vol = bars.slice(0, ORB_MINUTES).reduce((s, b) => s + b.v, 0);
      const priorVols = priorVolsByTicker.get(ticker)!;
      const avg = priorVols.length > 0 ? priorVols.reduce((a, b) => a + b, 0) / priorVols.length : todayFirst5Vol;
      const rvol = avg > 0 ? todayFirst5Vol / avg : 1;

      contexts.push(ctx);
      intradayByTicker.set(ticker, bars);
      rvolByTicker.set(ticker, rvol);

      // Update rolling window
      priorVols.push(todayFirst5Vol);
      if (priorVols.length > 14) priorVols.shift();
    }

    if (contexts.length > 0) {
      dayDataMap.set(date, { contexts, intradayByTicker, rvolByTicker });
    }
  }

  console.log(`[research] ${dayDataMap.size} tradable days precomputed.\n`);

  // ─── Sweep ───
  console.log("╔══════════════════════════════════════════════════════════════════════════════════════════╗");
  console.log("║       ZARATTINI-STYLE ORB BACKTEST — Hold-to-EOD with Large R Targets                  ║");
  console.log("╚══════════════════════════════════════════════════════════════════════════════════════════╝");
  console.log("");
  console.log("  Position size: 1% of equity (compounded) | Starting capital: $100,000\n");
  console.log(`  ${"CONFIG".padEnd(28)} ${"#".padEnd(5)} ${"WIN%".padEnd(5)} ${"AVG+".padEnd(7)} ${"AVG-".padEnd(7)} ${"TOTAL R".padEnd(9)} ${"PF".padEnd(6)} ${"P&L 1%".padEnd(11)} MaxDD`);
  console.log("  " + "─".repeat(95));

  let bestR = -Infinity, bestCfg = "";
  const allResults: { cfg: ResearchConfig; trades: Trade[]; totalR: number }[] = [];

  for (const cfg of CONFIGS) {
    const trades: Trade[] = [];
    for (const [date, dd] of dayDataMap) {
      trades.push(...simulateDay(date, dd.contexts, dd.intradayByTicker, dd.rvolByTicker, cfg));
    }
    reportConfig(cfg, trades);
    const totalR = trades.reduce((s, t) => s + t.rMultiple, 0);
    allResults.push({ cfg, trades, totalR });
    if (totalR > bestR) { bestR = totalR; bestCfg = cfg.name; }
  }

  console.log("  " + "─".repeat(95));
  console.log(`  BEST: ${bestCfg} → ${bestR >= 0 ? "+" : ""}${bestR.toFixed(2)}R\n`);

  // Best config detail
  const best = allResults.find(r => r.cfg.name === bestCfg)!;

  console.log("\n── BEST CONFIG: Per-ticker breakdown ──");
  for (const ticker of BT_TICKERS) {
    for (const dir of ["LONG", "SHORT"] as const) {
      const tt = best.trades.filter(t => t.ticker === ticker && t.direction === dir);
      if (tt.length === 0) continue;
      const tw = tt.filter(t => t.rMultiple > 0.2).length;
      const tr = tt.reduce((s, t) => s + t.rMultiple, 0);
      console.log(`  ${(ticker + " " + dir).padEnd(15)} ${String(tt.length).padEnd(5)} ${(((tw / tt.length) * 100).toFixed(1) + "%").padEnd(8)} ${(tr >= 0 ? "+" : "") + tr.toFixed(2)}R`);
    }
  }

  // Top winners
  console.log("\n── TOP 15 BIGGEST WINNERS (best config) ──");
  const sortedR = [...best.trades].sort((a, b) => b.rMultiple - a.rMultiple);
  for (const t of sortedR.slice(0, 15)) {
    console.log(`  ${t.date}  ${t.ticker.padEnd(6)} ${t.direction.padEnd(6)} entry $${t.entryPrice.toFixed(2)} → exit $${t.exitPrice.toFixed(2)}  ${(t.rMultiple >= 0 ? "+" : "") + t.rMultiple.toFixed(2)}R  ${t.exitType}  (${t.barsHeld} bars)`);
  }

  console.log("\n── EXIT TYPE BREAKDOWN (best config) ──");
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
