/**
 * ULTIMATE Backtest — 2-year Zarattini ORB with:
 *  - Expanded universe (high-beta + leveraged ETFs as futures proxies)
 *  - Top-N "Stocks in Play" daily rotation (RVOL ranking)
 *  - VIX-style regime filter
 *  - All winning configs from prior research
 *
 * Note: Leveraged ETFs (TQQQ, SOXL, etc.) act as ~3x futures proxies with
 *       similar volatility behavior. TQQQ tracks NQ futures behavior closely.
 */

import { ALPACA_REST_URL } from "@/lib/constants";
import { calcATR, calcSMA } from "@/lib/indicators";
import type { AlpacaBar, Direction } from "@/lib/types";

// ── UNIVERSE ──
// Core ORB tickers (proven winners)
const CORE_TICKERS = ["SPY", "QQQ", "AAPL", "TSLA", "NVDA", "AMD"];
// Leveraged ETFs as futures proxies (3x exposure → big ORB moves)
const LEVERAGED_ETF = ["TQQQ", "UPRO", "SOXL", "FAS", "TNA"];
// High-beta names that often appear in "stocks in play"
const HIGH_BETA = ["MSTR", "COIN", "PLTR", "SMCI", "ARM", "MARA"];

const BT_TICKERS = [...CORE_TICKERS, ...LEVERAGED_ETF, ...HIGH_BETA];

// ── DATE RANGE: 2 years ──
const START_DATE = "2024-06-09";
const END_DATE = "2026-06-09";
const CONTEXT_START = "2024-04-01";

const ORB_MINUTES = 5;

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
    const url = `${ALPACA_REST_URL}/v2/stocks/bars?${params}`;
    const res = await fetch(url, { headers: headers() });
    if (!res.ok) {
      console.error(`  [${symbol}] ${res.status}`);
      return [];
    }
    const data = await res.json();
    const bars: AlpacaBar[] = data.bars?.[symbol] ?? [];
    all.push(...bars);
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

interface DayContext {
  ticker: string;
  atr14: number;
  avgVol5Day: number;
  gapPct: number;
  isNR7: boolean;
  rvol: number; // first 5-min RVOL vs 14-day avg first 5-min
}

interface Trade {
  date: string; ticker: string; direction: Direction;
  entryPrice: number; stopPrice: number; risk: number;
  exitPrice: number; exitType: string;
  rMultiple: number; barsHeld: number;
  rvol: number;
}

interface UltimateConfig {
  name: string;
  targetMultiplier: number;
  holdToEOD: boolean;
  useBreakeven: boolean;
  partialTakeProfit: boolean;
  requireVWAPAlign: boolean;
  requireStrongClose: boolean;
  dirFilter: Set<string> | null;
  tickerFilter: Set<string> | null;
  topN_RVOL: number;
  maxTradesPerDay: number;
  dailyLossLimitR: number;
  minRVOL: number;
  minAtrPct: number;
  maxAtrPct: number;
  mwfOnly: boolean;             // Mon/Wed/Fri only filter
  optionsMode: boolean;         // Simulate as 0DTE option trades (SPY/QQQ only)
}

const DEFAULT_CFG: UltimateConfig = {
  name: "default",
  targetMultiplier: 3,
  holdToEOD: true,
  useBreakeven: false,
  partialTakeProfit: false,
  requireVWAPAlign: false,
  requireStrongClose: false,
  dirFilter: null,
  tickerFilter: null,
  topN_RVOL: 0,
  maxTradesPerDay: 0,
  dailyLossLimitR: 0,
  minRVOL: 0,
  minAtrPct: 0,
  maxAtrPct: 0,
  mwfOnly: false,
  optionsMode: false,
};

function computeContext(
  ticker: string,
  dailyBars: AlpacaBar[],
  dayIdx: number,
  openPrice: number,
  first5MinVol: number,
  prior14First5MinVols: number[],
): DayContext | null {
  if (dayIdx < 15) return null;
  const prior = dailyBars.slice(Math.max(0, dayIdx - 30), dayIdx);
  if (prior.length < 15) return null;

  const hlc = prior.map(b => ({ high: b.h, low: b.l, close: b.c }));
  const atr14 = calcATR(hlc, 14);
  if (atr14 <= 0) return null;

  const avgVol5Day = prior.slice(-5).reduce((s, b) => s + b.v, 0) / 5;

  const priorClose = dailyBars[dayIdx - 1].c;
  const gapPct = ((openPrice - priorClose) / priorClose) * 100;

  // NR7: today's range smaller than last 7
  const last7Ranges = prior.slice(-7).map(b => b.h - b.l);
  const todayRange = openPrice * 0.02; // estimate
  const isNR7 = todayRange < Math.min(...last7Ranges);

  // RVOL: first 5-min volume vs 14-day avg first 5-min volume
  const avgFirst5MinVol = prior14First5MinVols.length > 0
    ? prior14First5MinVols.reduce((s, v) => s + v, 0) / prior14First5MinVols.length
    : first5MinVol;
  const rvol = avgFirst5MinVol > 0 ? first5MinVol / avgFirst5MinVol : 1.0;

  return { ticker, atr14, avgVol5Day, gapPct, isNR7, rvol };
}

function simulateDay(
  date: string,
  contexts: DayContext[],
  intradayByTicker: Map<string, AlpacaBar[]>,
  cfg: UltimateConfig,
): Trade[] {
  // MWF only filter (Mon=1, Wed=3, Fri=5)
  if (cfg.mwfOnly) {
    const dow = new Date(date + "T12:00:00Z").getUTCDay();
    if (dow !== 1 && dow !== 3 && dow !== 5) return [];
  }

  const trades: Trade[] = [];
  let dayR = 0, dayTrades = 0;

  // Filter / sort by topN_RVOL
  let workingContexts = contexts;
  if (cfg.topN_RVOL > 0) {
    workingContexts = [...contexts].sort((a, b) => b.rvol - a.rvol).slice(0, cfg.topN_RVOL);
  }

  for (const ctx of workingContexts) {
    if (cfg.dailyLossLimitR > 0 && dayR <= -cfg.dailyLossLimitR) break;
    if (cfg.maxTradesPerDay > 0 && dayTrades >= cfg.maxTradesPerDay) break;
    if (cfg.tickerFilter && !cfg.tickerFilter.has(ctx.ticker)) continue;
    if (cfg.minRVOL > 0 && ctx.rvol < cfg.minRVOL) continue;

    const bars = intradayByTicker.get(ctx.ticker);
    if (!bars || bars.length < ORB_MINUTES + 30) continue;

    // ATR regime filter (low/high vol)
    const openPrice = bars[0].o;
    const atrPct = (ctx.atr14 / openPrice) * 100;
    if (cfg.minAtrPct > 0 && atrPct < cfg.minAtrPct) continue;
    if (cfg.maxAtrPct > 0 && atrPct > cfg.maxAtrPct) continue;

    // ORB
    const rb = bars.slice(0, ORB_MINUTES);
    const rangeHigh = Math.max(...rb.map(b => b.h));
    const rangeLow = Math.min(...rb.map(b => b.l));
    const rangeWidth = rangeHigh - rangeLow;
    if (rangeWidth <= 0) continue;

    const firstOpen = rb[0].o;
    const firstClose = rb[rb.length - 1].c;
    if (Math.abs(firstClose - firstOpen) < rangeWidth * 0.1) continue;
    const candleDir: Direction = firstClose > firstOpen ? "LONG" : "SHORT";

    if (cfg.dirFilter && !cfg.dirFilter.has(`${ctx.ticker} ${candleDir}`)) continue;

    // VWAP from session start
    let vp = 0, vol = 0;
    for (const b of rb) { vp += ((b.h + b.l + b.c) / 3) * b.v; vol += b.v; }

    // Find breakout
    let entryBar = -1, entryPrice = 0;
    for (let i = ORB_MINUTES; i < Math.min(60, bars.length); i++) {
      const b = bars[i];
      vp += ((b.h + b.l + b.c) / 3) * b.v;
      vol += b.v;

      if (candleDir === "LONG" && b.c > rangeHigh) {
        if (cfg.requireStrongClose) {
          const r = b.h - b.l;
          if (r > 0 && (b.c - b.l) / r < 0.7) continue;
        }
        entryBar = i; entryPrice = b.c; break;
      }
      if (candleDir === "SHORT" && b.c < rangeLow) {
        if (cfg.requireStrongClose) {
          const r = b.h - b.l;
          if (r > 0 && (b.h - b.c) / r < 0.7) continue;
        }
        entryBar = i; entryPrice = b.c; break;
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

    // ── OPTIONS MODE: SPY/QQQ only, simulate as 0DTE ATM ──
    // Rules: entry = $500 premium (flat), stop at -50% option, target at +100% option, 3:30 PM time exit
    // Option value approx: ATM 0DTE ~= S * 0.18 * sqrt(6.5/(252*24)) * 0.4 ≈ S * 0.0011 per leg
    // When S moves X% in our direction, option value moves ~X * delta * 100 (delta ≈ 0.5 ATM)
    // Theta decay ≈ 8%/hour for 0DTE
    if (cfg.optionsMode) {
      if (!["SPY", "QQQ"].includes(ctx.ticker)) continue; // 0DTE only liquid on indices
      // Skip if not MWF (already handled but enforce)
      const dow = new Date(date + "T12:00:00Z").getUTCDay();
      if (dow !== 1 && dow !== 3 && dow !== 5) continue;

      // Find 3:30 PM bar (close 30 min before EOD)
      let timeExitBar = bars.length - 1;
      for (let i = entryBar + 1; i < bars.length; i++) {
        const et = barET(bars[i]);
        if (et.h === 15 && et.m >= 30) { timeExitBar = i; break; }
      }

      // Simulate option P&L
      // Approximation: option_pct = (underlying_move_in_R) * sensitivity - theta_decay
      // For ATM 0DTE: 1R underlying move (one range width) ≈ ~80% option move (delta * leverage)
      // Theta: ~8% per hour
      const sensitivity = 0.8; // option gain per R of underlying move
      const thetaPerHour = 0.08;

      let opt_exit_pct = 0;
      let opt_exit_type = "time";
      let opt_exit_bar = timeExitBar;
      let opt_best_pct = 0;

      for (let i = entryBar + 1; i <= timeExitBar; i++) {
        const b = bars[i];
        const hoursPassed = (i - entryBar) / 60;
        const decayPct = Math.min(0.95, hoursPassed * thetaPerHour);

        // Track high-water and low-water option values during the bar
        const upMove = candleDir === "LONG" ? (b.h - entryPrice) / risk : (entryPrice - b.l) / risk;
        const downMove = candleDir === "LONG" ? (b.l - entryPrice) / risk : (entryPrice - b.h) / risk;

        const optHigh = (upMove * sensitivity) - decayPct;
        const optLow = (downMove * sensitivity) - decayPct;
        opt_best_pct = Math.max(opt_best_pct, optHigh);

        // Stop loss check (-50% of premium)
        if (optLow <= -0.5) {
          opt_exit_pct = -0.5;
          opt_exit_type = "opt_stop";
          opt_exit_bar = i;
          break;
        }
        // Target check (+100% of premium)
        if (optHigh >= 1.0) {
          opt_exit_pct = 1.0;
          opt_exit_type = "opt_target";
          opt_exit_bar = i;
          break;
        }
      }

      if (opt_exit_type === "time") {
        // Time stop at 3:30 PM - calculate final option value
        const hoursPassed = (timeExitBar - entryBar) / 60;
        const decayPct = Math.min(0.95, hoursPassed * thetaPerHour);
        const finalBar = bars[timeExitBar];
        const finalMove = candleDir === "LONG"
          ? (finalBar.c - entryPrice) / risk
          : (entryPrice - finalBar.c) / risk;
        opt_exit_pct = (finalMove * sensitivity) - decayPct;
        opt_exit_pct = Math.max(-1.0, opt_exit_pct); // can't lose more than premium
      }

      // Convert to "R" for compounding consistency (1% premium risk per trade)
      // -50% loss = -0.5R, +100% win = +1.0R
      trades.push({
        date, ticker: ctx.ticker, direction: candleDir,
        entryPrice, stopPrice, risk,
        exitPrice: entryPrice + opt_exit_pct * risk, // synthetic
        exitType: opt_exit_type,
        rMultiple: opt_exit_pct,
        barsHeld: opt_exit_bar - entryBar,
        rvol: ctx.rvol,
      });
      dayR += opt_exit_pct;
      dayTrades++;
      continue; // skip normal simulation
    }

    // Simulate
    let exitPrice = 0, exitType = "eod", curStop = stopPrice;
    let bestReachedR = 0, exitBar = bars.length - 1;
    let partialTaken = false, partialR = 0;

    for (let i = entryBar + 1; i < bars.length; i++) {
      const b = bars[i];
      const unrealized = candleDir === "LONG"
        ? (b.h - entryPrice) / risk
        : (entryPrice - b.l) / risk;
      bestReachedR = Math.max(bestReachedR, unrealized);

      if (cfg.partialTakeProfit && !partialTaken && bestReachedR >= 1.0) {
        partialTaken = true; partialR = 0.5; curStop = entryPrice;
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
      exitPrice = bars[bars.length - 1].c;
      exitType = "eod";
    }

    const pnl = candleDir === "LONG" ? exitPrice - entryPrice : entryPrice - exitPrice;
    const remainderR = pnl / risk;
    const rMul = cfg.partialTakeProfit && partialTaken
      ? partialR + 0.5 * remainderR
      : remainderR;

    trades.push({
      date, ticker: ctx.ticker, direction: candleDir,
      entryPrice, stopPrice, risk,
      exitPrice, exitType, rMultiple: rMul,
      barsHeld: exitBar - entryBar,
      rvol: ctx.rvol,
    });
    dayR += rMul;
    dayTrades++;
  }
  return trades;
}

function compoundEquity(trades: Trade[], startCapital: number, riskPct: number) {
  const sorted = [...trades].sort((a, b) => a.date.localeCompare(b.date));
  let equity = startCapital, peak = startCapital, maxDD = 0, low = startCapital;
  for (const t of sorted) {
    const pnl = (equity * riskPct) * t.rMultiple;
    equity += pnl;
    if (equity > peak) peak = equity;
    const dd = peak - equity;
    if (dd > maxDD) maxDD = dd;
    if (equity < low) low = equity;
  }
  return { endEquity: equity, maxDDDollars: maxDD, lowEquity: low };
}

function fmt$(n: number): string {
  const s = n >= 0 ? "+" : "-";
  return s + "$" + Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function reportConfig(cfg: UltimateConfig, trades: Trade[]) {
  const W = trades.filter(t => t.rMultiple > 0.2);
  const L = trades.filter(t => t.rMultiple < -0.2);
  const totalR = trades.reduce((s, t) => s + t.rMultiple, 0);
  const winRate = trades.length > 0 ? (W.length / trades.length) * 100 : 0;
  const grossWin = W.reduce((s, t) => s + t.rMultiple, 0);
  const grossLoss = Math.abs(L.reduce((s, t) => s + t.rMultiple, 0));
  const pf = grossLoss > 0 ? grossWin / grossLoss : 0;
  const r1 = compoundEquity(trades, 100_000, 0.01);
  console.log(`  ${cfg.name.padEnd(34)} ${String(trades.length).padEnd(5)} ${(winRate.toFixed(0) + "%").padEnd(5)} ${((totalR >= 0 ? "+" : "") + totalR.toFixed(1) + "R").padEnd(9)} ${(pf.toFixed(2) + "x").padEnd(6)} ${fmt$(r1.endEquity - 100_000).padEnd(11)} -$${r1.maxDDDollars.toLocaleString("en-US", { maximumFractionDigits: 0 })}`);
}

// Winners identified from prior 1-year research
const STOCK_WINNERS = new Set([
  "SPY LONG", "SPY SHORT", "QQQ LONG", "QQQ SHORT",
  "AMD LONG", "AMD SHORT", "TSLA LONG", "TSLA SHORT", "NVDA LONG",
  // Leveraged ETF winners (assumed similar to underlying)
  "TQQQ LONG", "TQQQ SHORT", "UPRO LONG", "SOXL LONG", "SOXL SHORT",
  "FAS LONG", "TNA LONG",
  // High-beta
  "MSTR LONG", "MSTR SHORT", "COIN LONG", "PLTR LONG", "SMCI LONG", "SMCI SHORT",
]);

const CONFIGS: UltimateConfig[] = [
  // ── PRIOR BEST (for comparison) ──
  { ...DEFAULT_CFG, name: "BEST 1yr: 3R top5+win+DLL3", targetMultiplier: 3, topN_RVOL: 5, dirFilter: STOCK_WINNERS, dailyLossLimitR: 3 },
  { ...DEFAULT_CFG, name: "3R top5+winners+partial", targetMultiplier: 3, topN_RVOL: 5, dirFilter: STOCK_WINNERS, partialTakeProfit: true },

  // ── ADD MWF FILTER (Mon/Wed/Fri only) ──
  { ...DEFAULT_CFG, name: "MWF: 3R top5+win+DLL3", targetMultiplier: 3, topN_RVOL: 5, dirFilter: STOCK_WINNERS, dailyLossLimitR: 3, mwfOnly: true },
  { ...DEFAULT_CFG, name: "MWF: 3R top5+win+partial", targetMultiplier: 3, topN_RVOL: 5, dirFilter: STOCK_WINNERS, partialTakeProfit: true, mwfOnly: true },
  { ...DEFAULT_CFG, name: "MWF: 3R top10+winners", targetMultiplier: 3, topN_RVOL: 10, dirFilter: STOCK_WINNERS, mwfOnly: true },
  { ...DEFAULT_CFG, name: "MWF: 10R top5+winners", targetMultiplier: 10, topN_RVOL: 5, dirFilter: STOCK_WINNERS, mwfOnly: true },
  { ...DEFAULT_CFG, name: "MWF: 3R+EOD ATR%<3", targetMultiplier: 3, maxAtrPct: 3.0, mwfOnly: true },
  { ...DEFAULT_CFG, name: "MWF: 3R RVOL>2.0", targetMultiplier: 3, minRVOL: 2.0, mwfOnly: true },

  // ── LEVERAGED ETFs ONLY (futures proxy) with MWF ──
  { ...DEFAULT_CFG, name: "MWF: 3R LevETF only", targetMultiplier: 3, tickerFilter: new Set(LEVERAGED_ETF), mwfOnly: true },
  { ...DEFAULT_CFG, name: "MWF: 10R LevETF only", targetMultiplier: 10, tickerFilter: new Set(LEVERAGED_ETF), mwfOnly: true },

  // ── 0DTE OPTIONS MODE — SPY only, ATM, -50%/+100%/3:30PM ──
  { ...DEFAULT_CFG, name: "OPT 0DTE SPY+QQQ all days", targetMultiplier: 3, tickerFilter: new Set(["SPY", "QQQ"]), optionsMode: true },
  { ...DEFAULT_CFG, name: "OPT 0DTE SPY+QQQ MWF only ⭐", targetMultiplier: 3, tickerFilter: new Set(["SPY", "QQQ"]), optionsMode: true, mwfOnly: true },
  { ...DEFAULT_CFG, name: "OPT 0DTE SPY only MWF", targetMultiplier: 3, tickerFilter: new Set(["SPY"]), optionsMode: true, mwfOnly: true },
  { ...DEFAULT_CFG, name: "OPT 0DTE QQQ only MWF", targetMultiplier: 3, tickerFilter: new Set(["QQQ"]), optionsMode: true, mwfOnly: true },

  // ── STACK: stocks + options together ──
  // (we run both modes separately and add them)
];

async function main() {
  if (!process.env.ALPACA_API_KEY) throw new Error("Set ALPACA_API_KEY");

  console.log("[ultimate] 2-YEAR ULTIMATE BACKTEST");
  console.log(`[ultimate] Period: ${START_DATE} → ${END_DATE}`);
  console.log(`[ultimate] Universe: ${BT_TICKERS.length} tickers`);
  console.log(`  Core: ${CORE_TICKERS.join(", ")}`);
  console.log(`  LevETF: ${LEVERAGED_ETF.join(", ")}`);
  console.log(`  HighBeta: ${HIGH_BETA.join(", ")}\n`);

  // Fetch daily bars
  console.log("[ultimate] Fetching daily bars...");
  const dailyByTicker = new Map<string, AlpacaBar[]>();
  for (const ticker of BT_TICKERS) {
    const bars = await fetchStockBars(ticker, "1Day", CONTEXT_START, END_DATE);
    dailyByTicker.set(ticker, bars);
    console.log(`  ${ticker.padEnd(6)} ${bars.length} bars`);
  }

  // Fetch 1-min bars
  console.log("\n[ultimate] Fetching 1-min intraday bars (this takes a few mins)...");
  const allMinBars = new Map<string, AlpacaBar[]>();
  for (const ticker of BT_TICKERS) {
    const bars = await fetchStockBars(ticker, "1Min", START_DATE, END_DATE);
    allMinBars.set(ticker, bars);
    const days = new Set(bars.filter(isMarketHours).map(barDateET)).size;
    console.log(`  ${ticker.padEnd(6)} ${bars.length} bars (${days} days)`);
  }

  // Group intraday bars by date
  console.log("\n[ultimate] Processing intraday data...");
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

  const tradingDays = getTradingDays(START_DATE, END_DATE).sort();

  // Precompute first5MinVol per ticker per day (for RVOL calc)
  const first5VolByTickerDay = new Map<string, Map<string, number>>();
  for (const [ticker, _] of dailyByTicker) first5VolByTickerDay.set(ticker, new Map());
  for (const [date, tm] of dayBarsMap) {
    for (const [ticker, bars] of tm) {
      const first5 = bars.slice(0, 5).reduce((s, b) => s + b.v, 0);
      first5VolByTickerDay.get(ticker)?.set(date, first5);
    }
  }

  // Precompute contexts
  interface DayData { contexts: DayContext[]; intradayByTicker: Map<string, AlpacaBar[]>; }
  const dayDataMap = new Map<string, DayData>();

  for (let dayI = 0; dayI < tradingDays.length; dayI++) {
    const date = tradingDays[dayI];
    const dayBars = dayBarsMap.get(date);
    if (!dayBars) continue;

    const contexts: DayContext[] = [];
    const intradayByTicker = new Map<string, AlpacaBar[]>();

    for (const ticker of BT_TICKERS) {
      const bars = dayBars.get(ticker);
      if (!bars || bars.length < ORB_MINUTES + 30) continue;
      const dailyIdx = dailyDateIdx.get(date)?.get(ticker);
      const daily = dailyByTicker.get(ticker);
      if (dailyIdx === undefined || !daily) continue;

      // Get prior 14 days of first-5-min volume for RVOL
      const prior14First5: number[] = [];
      for (let j = Math.max(0, dayI - 14); j < dayI; j++) {
        const v = first5VolByTickerDay.get(ticker)?.get(tradingDays[j]);
        if (v !== undefined) prior14First5.push(v);
      }
      const today5 = bars.slice(0, 5).reduce((s, b) => s + b.v, 0);
      const openPrice = bars[0].o;

      const ctx = computeContext(ticker, daily, dailyIdx, openPrice, today5, prior14First5);
      if (!ctx) continue;
      contexts.push(ctx);
      intradayByTicker.set(ticker, bars);
    }

    if (contexts.length > 0) dayDataMap.set(date, { contexts, intradayByTicker });
  }

  console.log(`[ultimate] ${dayDataMap.size} tradable days precomputed (${tradingDays.length} total).\n`);

  console.log("╔══════════════════════════════════════════════════════════════════════════════════════════════╗");
  console.log("║       2-YEAR ULTIMATE BACKTEST — Expanded Universe + Stocks-in-Play + Regime Filter         ║");
  console.log("╚══════════════════════════════════════════════════════════════════════════════════════════════╝");
  console.log("\n  Position size: 1% equity (compounded) | Starting capital: $100,000\n");
  console.log(`  ${"CONFIG".padEnd(34)} ${"#".padEnd(5)} ${"WIN%".padEnd(5)} ${"TOTAL R".padEnd(9)} ${"PF".padEnd(6)} ${"P&L 1%".padEnd(11)} MaxDD`);
  console.log("  " + "─".repeat(95));

  const allResults: { cfg: UltimateConfig; trades: Trade[]; totalR: number }[] = [];
  let bestR = -Infinity, bestCfg = "";

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

  // Per-ticker breakdown for top 3 configs
  const top3 = [...allResults].sort((a, b) => b.totalR - a.totalR).slice(0, 3);
  for (const r of top3) {
    console.log(`\n── ${r.cfg.name} (${r.trades.length} trades, ${r.totalR.toFixed(2)}R) ──`);
    const tickers = new Set(r.trades.map(t => t.ticker));
    for (const t of Array.from(tickers).sort()) {
      for (const dir of ["LONG", "SHORT"] as const) {
        const tt = r.trades.filter(x => x.ticker === t && x.direction === dir);
        if (tt.length === 0) continue;
        const tw = tt.filter(x => x.rMultiple > 0.2).length;
        const tr = tt.reduce((s, x) => s + x.rMultiple, 0);
        console.log(`  ${(t + " " + dir).padEnd(15)} ${String(tt.length).padEnd(5)} ${(((tw / tt.length) * 100).toFixed(1) + "%").padEnd(8)} ${(tr >= 0 ? "+" : "") + tr.toFixed(2)}R`);
      }
    }
  }
}

main().catch(console.error);
