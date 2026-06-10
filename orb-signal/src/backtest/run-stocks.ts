import { ALPACA_REST_URL } from "@/lib/constants";
import { calcSMA, calcATR, calcVWAP, calcEMA, calcSMASlope } from "@/lib/indicators";
import { gradeRange } from "@/engine/quality-gate";
import { checkBreakout } from "@/engine/breakout-detector";
import { calcCompositeScore, selectTrades } from "@/engine/ranking";
import { checkExit, calcTrailingStop } from "@/engine/exit-tracker";
import type { AlpacaBar, Grade, Direction } from "@/lib/types";

// ═══════════════════════════════════════════════════════════════
// CONFIG
// ═══════════════════════════════════════════════════════════════
const BT_TICKERS = ["SPY", "QQQ", "AAPL", "TSLA", "NVDA", "AMD"];
const START_DATE = "2025-06-09";
const END_DATE = "2026-06-09";
const CONTEXT_START = "2025-04-01";
const TIMEFRAMES = [10] as const;

const DEFAULTS = {
  maxRangeAtrPct: 75,
  smaDowngradeThreshold: 0.5,
  smaSlopSkipThreshold: 0.2,
  candleQualityThreshold: 0.3,
  minVolumeRatio: 0.5,
  timeCutoffBars: 120,
  timeExitMinutes: 120,
  maxTradesPerDay: 3,
  secondTradeScoreGap: 2,
  selectionDelayBars: 1,
  failurePatience: 1,
  breakevenThresholdR: 0.15,
  minBreakoutVolume: 1.0,
  minCompositeScore: 7,
  targetMultiplier: 1.0,
  earlyTrail: false,
};

// ═══════════════════════════════════════════════════════════════
// DATA FETCHING — Stock API (different endpoint than crypto)
// ═══════════════════════════════════════════════════════════════
function headers() {
  return {
    "APCA-API-KEY-ID": process.env.ALPACA_API_KEY!,
    "APCA-API-SECRET-KEY": process.env.ALPACA_API_SECRET!,
  };
}

async function fetchStockBars(symbol: string, timeframe: string, start: string, end: string): Promise<AlpacaBar[]> {
  const allBars: AlpacaBar[] = [];
  let pageToken: string | null = null;

  do {
    const params = new URLSearchParams({
      symbols: symbol, timeframe, start, end, limit: "10000", sort: "asc",
      feed: "iex", // free tier uses IEX feed
    });
    if (pageToken) params.set("page_token", pageToken);

    const url = `${ALPACA_REST_URL}/v2/stocks/bars?${params}`;
    const res = await fetch(url, { headers: headers() });
    if (!res.ok) {
      const txt = await res.text();
      console.error(`  [${symbol}] Alpaca ${res.status}: ${txt.slice(0, 200)}`);
      return [];
    }

    const data = await res.json();
    const bars: AlpacaBar[] = data.bars?.[symbol] ?? [];
    allBars.push(...bars);
    pageToken = data.next_page_token ?? null;
    if (pageToken) await new Promise(r => setTimeout(r, 200));
  } while (pageToken);

  return allBars;
}

// ═══════════════════════════════════════════════════════════════
// TIME HELPERS (stocks have real market hours, much simpler)
// ═══════════════════════════════════════════════════════════════
function etOffset(d: Date): number {
  const m = d.getUTCMonth(), day = d.getUTCDate();
  if (m < 2 || m > 10) return 5;
  if (m > 2 && m < 10) return 4;
  if (m === 2) return day >= 9 ? 4 : 5;
  return day < 2 ? 4 : 5;
}

function barETHour(bar: AlpacaBar): { h: number; m: number } {
  const d = new Date(bar.t);
  const off = etOffset(d);
  return { h: d.getUTCHours() - off, m: d.getUTCMinutes() };
}

function isMarketHours(bar: AlpacaBar): boolean {
  const et = barETHour(bar);
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
    if (d.getUTCDay() >= 1 && d.getUTCDay() <= 5) {
      days.push(d.toISOString().split("T")[0]);
    }
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return days;
}

// ═══════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════
interface DayContext {
  ticker: string;
  sma20: number;
  atr14: number;
  smaSlope: number;
  priorClose: number;
  openPrice: number;
  gapPct: number;
  gapDirection: "UP" | "DOWN" | "FLAT";
}

interface Trade {
  date: string;
  ticker: string;
  timeframe: number;
  direction: Direction;
  grade: Grade;
  entryPrice: number;
  stopPrice: number;
  targetPrice: number;
  risk: number;
  exitPrice: number;
  exitType: string;
  outcome: "WIN" | "LOSS" | "SCRATCH";
  rMultiple: number;
  score: number;
}

// ═══════════════════════════════════════════════════════════════
// SIMULATION (same logic as crypto backtester)
// ═══════════════════════════════════════════════════════════════
function computeContext(ticker: string, dailyBars: AlpacaBar[], dayIdx: number, openPrice: number): DayContext | null {
  if (dayIdx < 20) return null;
  const prior = dailyBars.slice(Math.max(0, dayIdx - 40), dayIdx);
  if (prior.length < 15) return null;

  const closes = prior.map(b => b.c);
  const sma20 = calcSMA(closes, 20);
  if (isNaN(sma20)) return null;

  const hlc = prior.map(b => ({ high: b.h, low: b.l, close: b.c }));
  const atr14 = calcATR(hlc, 14);
  if (atr14 <= 0) return null;

  const smaVals: number[] = [];
  for (let i = Math.max(5, closes.length - 5); i <= closes.length; i++) {
    const sl = closes.slice(0, i);
    if (sl.length >= 20) smaVals.push(calcSMA(sl, 20));
  }
  const smaSlope = smaVals.length >= 2 ? calcSMASlope(smaVals) : 0;

  const priorClose = dailyBars[dayIdx - 1].c;
  const gapPct = ((openPrice - priorClose) / priorClose) * 100;
  const gapDir = gapPct > 0.1 ? "UP" as const : gapPct < -0.1 ? "DOWN" as const : "FLAT" as const;

  return { ticker, sma20, atr14, smaSlope, priorClose, openPrice, gapPct, gapDirection: gapDir };
}

interface ConfigOverrides {
  targetMultiplier?: number;
  minCompositeScore?: number;
  dirFilter?: Set<string> | null;  // "TICKER DIR" e.g. "AMD SHORT"
  tickerFilter?: Set<string> | null; // just ticker names
}

function simulateDay(
  date: string,
  contexts: DayContext[],
  intradayByTicker: Map<string, AlpacaBar[]>,
  overrides: ConfigOverrides = {},
): Trade[] {
  const cfg = { ...DEFAULTS, ...overrides };
  interface RangeInfo {
    ticker: string; timeframe: number;
    rangeHigh: number; rangeLow: number; rangeWidth: number;
    volume: number; grade: string; skipReason: string | null;
    rangeAtrPct: number;
  }

  const ranges: RangeInfo[] = [];
  for (const ctx of contexts) {
    const bars = intradayByTicker.get(ctx.ticker);
    if (!bars || bars.length < 16) continue;

    for (const tf of TIMEFRAMES) {
      const rb = bars.slice(0, tf);
      if (rb.length < tf) continue;

      const rangeHigh = Math.max(...rb.map(b => b.h));
      const rangeLow = Math.min(...rb.map(b => b.l));
      const rangeWidth = rangeHigh - rangeLow;
      if (rangeWidth <= 0) continue;

      const vol = rb.reduce((s, b) => s + b.v, 0);
      const avgVol = bars.slice(0, 15).reduce((s, b) => s + b.v, 0) / 15 * tf;

      const q = gradeRange({ rangeWidth, atr14: ctx.atr14, volume: vol, avgVolume: avgVol, smaSlope: ctx.smaSlope });

      ranges.push({
        ticker: ctx.ticker, timeframe: tf,
        rangeHigh, rangeLow, rangeWidth, volume: vol,
        grade: q.grade, skipReason: q.skipReason, rangeAtrPct: q.rangeAtrPct,
      });
    }
  }

  const pending: any[] = [];
  let firstBkBar: number | null = null;
  const detected = new Set<string>();
  const vwapAcc = new Map<string, { vp: number; vol: number }>();
  for (const ctx of contexts) vwapAcc.set(ctx.ticker, { vp: 0, vol: 0 });

  const maxLen = Math.max(...Array.from(intradayByTicker.values()).map(b => b.length), 0);

  for (const [tk, bars] of intradayByTicker) {
    for (let i = 0; i < Math.min(16, bars.length); i++) {
      const b = bars[i];
      const a = vwapAcc.get(tk)!;
      if (a) { a.vp += ((b.h + b.l + b.c) / 3) * b.v; a.vol += b.v; }
    }
  }

  for (let bi = 16; bi < Math.min(maxLen, cfg.timeCutoffBars); bi++) {
    for (const [tk, bars] of intradayByTicker) {
      if (bi >= bars.length) continue;
      const b = bars[bi];
      const a = vwapAcc.get(tk);
      if (a) { a.vp += ((b.h + b.l + b.c) / 3) * b.v; a.vol += b.v; }
    }

    for (const rng of ranges) {
      if (rng.grade === "SKIP") continue;
      const key = `${rng.ticker}-${rng.timeframe}`;
      if (detected.has(key)) continue;
      const bars = intradayByTicker.get(rng.ticker);
      if (!bars || bi >= bars.length) continue;

      const bar = bars[bi];
      const ctx = contexts.find(c => c.ticker === rng.ticker)!;
      if (!ctx) continue;
      const acc = vwapAcc.get(rng.ticker);
      const vwap = acc && acc.vol > 0 ? acc.vp / acc.vol : 0;
      const avgBarVol = bars.slice(0, 15).reduce((s, b) => s + b.v, 0) / 15;

      const bo = checkBreakout({
        bar: { open: bar.o, high: bar.h, low: bar.l, close: bar.c, volume: bar.v },
        rangeHigh: rng.rangeHigh, rangeLow: rng.rangeLow,
        vwap, sma20: ctx.sma20, avgBarVolume: avgBarVol,
      });

      if (bo) {
        if (bo.volumeRatio < cfg.minBreakoutVolume) { detected.add(key); continue; }

        // Ticker filter
        if (cfg.tickerFilter && !cfg.tickerFilter.has(rng.ticker)) { detected.add(key); continue; }

        // Direction × ticker filter
        if (cfg.dirFilter && !cfg.dirFilter.has(`${rng.ticker} ${bo.direction}`)) { detected.add(key); continue; }

        const gapAligned = (bo.direction === "LONG" && ctx.gapDirection === "UP") ||
          (bo.direction === "SHORT" && ctx.gapDirection === "DOWN");
        const slopeDown = Math.abs(ctx.smaSlope) < cfg.smaDowngradeThreshold;

        const cs = calcCompositeScore({
          grade: rng.grade as Grade, gapAligned,
          smaSlope: ctx.smaSlope, direction: bo.direction,
          vwapDistance: bo.vwapDistance, breakoutVolumeRatio: bo.volumeRatio,
          candleQuality: bo.candleQuality, slopeDowngrade: slopeDown,
        });

        if (cs.total < cfg.minCompositeScore) { detected.add(key); continue; }

        const stop = bo.direction === "LONG" ? rng.rangeLow : rng.rangeHigh;
        const risk = bo.direction === "LONG" ? bo.entryPrice - rng.rangeLow : rng.rangeHigh - bo.entryPrice;
        if (risk <= 0) continue;

        const target = bo.direction === "LONG"
          ? bo.entryPrice + rng.rangeWidth * cfg.targetMultiplier
          : bo.entryPrice - rng.rangeWidth * cfg.targetMultiplier;

        pending.push({
          ticker: rng.ticker, timeframe: rng.timeframe,
          direction: bo.direction, grade: rng.grade as Grade,
          entryPrice: bo.entryPrice, stopPrice: stop, targetPrice: target, risk,
          score: cs.total, breakoutBar: bi,
          rangeHigh: rng.rangeHigh, rangeLow: rng.rangeLow, rangeWidth: rng.rangeWidth,
          gapAligned, smaSlope: ctx.smaSlope, rangeAtrPct: rng.rangeAtrPct, gapPct: ctx.gapPct,
        });
        detected.add(key);
        if (firstBkBar === null) firstBkBar = bi;
      }
    }

    if (firstBkBar !== null && bi >= firstBkBar + cfg.selectionDelayBars) break;
  }

  if (pending.length === 0) return [];

  const cands = pending.map((p: any, i: number) => ({ id: i, ticker: p.ticker, score: p.score, grade: p.grade }));
  const selected = selectTrades(cands);

  const trades: Trade[] = [];
  for (const sel of selected) {
    const p = pending[sel.id];
    const bars = intradayByTicker.get(p.ticker);
    if (!bars) continue;

    let targetHit = false;
    let curStop = p.stopPrice;
    const closeHist: number[] = [];
    for (let i = 0; i <= p.breakoutBar && i < bars.length; i++) closeHist.push(bars[i].c);

    let exitPrice = p.entryPrice;
    let exitType = "eod";
    let consecutiveFailures = 0;
    let bestReachedR = 0;

    for (let i = p.breakoutBar + 1; i < bars.length; i++) {
      const b = bars[i];
      closeHist.push(b.c);

      const unrealized = p.direction === "LONG"
        ? (b.h - p.entryPrice) / p.risk
        : (p.entryPrice - b.l) / p.risk;
      bestReachedR = Math.max(bestReachedR, unrealized);

      const breakevenActive = !targetHit && cfg.breakevenThresholdR > 0 && bestReachedR >= cfg.breakevenThresholdR;
      if (breakevenActive) curStop = p.entryPrice;

      const ema9 = closeHist.length >= 9 ? calcEMA(closeHist, 9) : p.entryPrice;
      const trail = targetHit ? calcTrailingStop(p.direction, ema9) : null;

      const ex = checkExit({
        direction: p.direction,
        entryPrice: p.entryPrice, stopPrice: curStop, targetPrice: p.targetPrice,
        rangeHigh: p.rangeHigh, rangeLow: p.rangeLow,
        targetHit, trailingStop: trail,
        bar: { high: b.h, low: b.l, close: b.c, volume: b.v },
        entryTime: new Date(bars[p.breakoutBar].t), now: new Date(b.t), ema9,
      });

      if (ex) {
        if (ex.type === "target" && !targetHit) { targetHit = true; curStop = p.entryPrice; continue; }
        if (ex.type === "failure") { consecutiveFailures++; if (consecutiveFailures < cfg.failurePatience) continue; }
        exitPrice = ex.price;
        exitType = ex.type;
        break;
      } else {
        consecutiveFailures = 0;
      }
    }

    const pnl = p.direction === "LONG" ? exitPrice - p.entryPrice : p.entryPrice - exitPrice;
    const rMul = p.risk > 0 ? pnl / p.risk : 0;
    const outcome = pnl > p.risk * 0.2 ? "WIN" as const : pnl < -p.risk * 0.2 ? "LOSS" as const : "SCRATCH" as const;

    trades.push({
      date, ticker: p.ticker, timeframe: p.timeframe,
      direction: p.direction, grade: p.grade,
      entryPrice: p.entryPrice, stopPrice: p.stopPrice,
      targetPrice: p.targetPrice, risk: p.risk,
      exitPrice, exitType, outcome, rMultiple: rMul, score: p.score,
    });
  }

  return trades;
}

// ═══════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════
// ═══════════════════════════════════════════════════════════════
// SWEEP CONFIGS
// ═══════════════════════════════════════════════════════════════
const SWEEP_CONFIGS: { name: string; overrides: ConfigOverrides }[] = [
  { name: "baseline", overrides: {} },
  { name: "SHORT only", overrides: { dirFilter: new Set(BT_TICKERS.flatMap(t => [`${t} SHORT`])) } },
  { name: "AMD only", overrides: { tickerFilter: new Set(["AMD"]) } },
  { name: "AMD+TSLA", overrides: { tickerFilter: new Set(["AMD", "TSLA"]) } },
  { name: "AMD-S only", overrides: { dirFilter: new Set(["AMD SHORT"]) } },
  { name: "AMD-S+AMD-L", overrides: { dirFilter: new Set(["AMD SHORT", "AMD LONG"]) } },
  { name: "SHORT+t=0.85", overrides: { dirFilter: new Set(BT_TICKERS.flatMap(t => [`${t} SHORT`])), targetMultiplier: 0.85 } },
  { name: "AMD+t=0.85", overrides: { tickerFilter: new Set(["AMD"]), targetMultiplier: 0.85 } },
  { name: "AMD-S+s≥7.5", overrides: { dirFilter: new Set(["AMD SHORT"]), minCompositeScore: 7.5 } },
  { name: "noSPY+noQQQ", overrides: { tickerFilter: new Set(["AAPL", "TSLA", "NVDA", "AMD"]) } },
  { name: "AMD-S+AAPL-L", overrides: { dirFilter: new Set(["AMD SHORT", "AMD LONG", "AAPL LONG"]) } },
  { name: "s≥7.5", overrides: { minCompositeScore: 7.5 } },
  { name: "t=0.85", overrides: { targetMultiplier: 0.85 } },
  { name: "t=0.85+s≥7.5", overrides: { targetMultiplier: 0.85, minCompositeScore: 7.5 } },
];

function compoundEquity(trades: Trade[], startCapital: number, riskPct: number): {
  endEquity: number; maxDDPct: number; maxDDDollars: number; peakEquity: number; lowEquity: number;
} {
  const sorted = [...trades].sort((a, b) => a.date.localeCompare(b.date));
  let equity = startCapital;
  let peak = startCapital;
  let maxDDPct = 0;
  let maxDDDollars = 0;
  let low = startCapital;

  for (const t of sorted) {
    const riskDollars = equity * riskPct;
    const pnl = riskDollars * t.rMultiple;
    equity += pnl;
    if (equity > peak) peak = equity;
    const ddPct = (peak - equity) / peak * 100;
    const ddDollars = peak - equity;
    if (ddPct > maxDDPct) maxDDPct = ddPct;
    if (ddDollars > maxDDDollars) maxDDDollars = ddDollars;
    if (equity < low) low = equity;
  }

  return { endEquity: equity, maxDDPct, maxDDDollars, peakEquity: peak, lowEquity: low };
}

function fmtMoney(n: number): string {
  const sign = n >= 0 ? "+" : "-";
  return sign + "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function reportConfig(name: string, trades: Trade[]) {
  const totalR = trades.reduce((s, t) => s + t.rMultiple, 0);
  const winRate = trades.length > 0 ? (trades.filter(t => t.outcome === "WIN").length / trades.length) * 100 : 0;
  const grossWin = trades.filter(t => t.rMultiple > 0).reduce((s, t) => s + t.rMultiple, 0);
  const grossLoss = Math.abs(trades.filter(t => t.rMultiple < 0).reduce((s, t) => s + t.rMultiple, 0));
  const pf = grossLoss > 0 ? grossWin / grossLoss : 0;

  const START = 100_000;
  const r05 = compoundEquity(trades, START, 0.005); // 0.5% risk
  const r1  = compoundEquity(trades, START, 0.01);  // 1% risk
  const r2  = compoundEquity(trades, START, 0.02);  // 2% risk

  console.log(`  ${name.padEnd(20)} ${String(trades.length).padEnd(4)} ${(winRate.toFixed(0) + "%").padEnd(5)} ${((totalR >= 0 ? "+" : "") + totalR.toFixed(2) + "R").padEnd(9)} ${(pf.toFixed(1) + "x").padEnd(6)} ${fmtMoney(r05.endEquity - START).padEnd(10)} ${fmtMoney(r1.endEquity - START).padEnd(10)} ${fmtMoney(r2.endEquity - START).padEnd(10)}`);
}

async function main() {
  if (!process.env.ALPACA_API_KEY) throw new Error("Set ALPACA_API_KEY");

  console.log("[stocks-backtest] ORB Stock Backtest SWEEP starting...");
  console.log(`[stocks-backtest] Period: ${START_DATE} → ${END_DATE}`);
  console.log(`[stocks-backtest] Tickers: ${BT_TICKERS.join(", ")}`);
  console.log("");

  // Fetch daily bars
  console.log("[stocks-backtest] Fetching daily bars...");
  const dailyByTicker = new Map<string, AlpacaBar[]>();
  for (const ticker of BT_TICKERS) {
    const bars = await fetchStockBars(ticker, "1Day", CONTEXT_START, END_DATE);
    dailyByTicker.set(ticker, bars);
    console.log(`  ${ticker}... ${bars.length} bars`);
  }

  // Fetch 1-min bars
  console.log("[stocks-backtest] Fetching 1-min intraday bars...");
  const allMinBars = new Map<string, AlpacaBar[]>();
  for (const ticker of BT_TICKERS) {
    const bars = await fetchStockBars(ticker, "1Min", START_DATE, END_DATE);
    allMinBars.set(ticker, bars);
    const days = new Set(bars.filter(isMarketHours).map(barDateET)).size;
    console.log(`  ${ticker}... ${bars.length} bars (${days} days)`);
  }

  // Group intraday bars by date
  console.log("[stocks-backtest] Processing intraday data...");
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

  // Build daily date index
  const dailyDateIdx = new Map<string, Map<string, number>>();
  for (const [ticker, bars] of dailyByTicker) {
    for (let i = 0; i < bars.length; i++) {
      const d = bars[i].t.split("T")[0];
      if (!dailyDateIdx.has(d)) dailyDateIdx.set(d, new Map());
      dailyDateIdx.get(d)!.set(ticker, i);
    }
  }

  const tradingDays = getTradingDays(START_DATE, END_DATE);

  // Precompute day contexts (shared across all sweeps)
  interface DayData { contexts: DayContext[]; intradayByTicker: Map<string, AlpacaBar[]>; }
  const dayDataMap = new Map<string, DayData>();

  for (const date of tradingDays) {
    const dayBars = dayBarsMap.get(date);
    if (!dayBars) continue;

    const contexts: DayContext[] = [];
    const intradayByTicker = new Map<string, AlpacaBar[]>();

    for (const ticker of BT_TICKERS) {
      const bars = dayBars.get(ticker);
      if (!bars || bars.length < 16) continue;

      const dailyIdx = dailyDateIdx.get(date)?.get(ticker);
      const daily = dailyByTicker.get(ticker);
      if (dailyIdx === undefined || !daily) continue;

      const openPrice = bars[0].o;
      const ctx = computeContext(ticker, daily, dailyIdx, openPrice);
      if (ctx) {
        contexts.push(ctx);
        intradayByTicker.set(ticker, bars);
      }
    }

    if (contexts.length > 0) dayDataMap.set(date, { contexts, intradayByTicker });
  }

  console.log(`[stocks-backtest] ${dayDataMap.size} tradable days precomputed.\n`);

  // ─── Sweep ───
  console.log("╔══════════════════════════════════════════════════════════════════════════════╗");
  console.log("║          ORB STOCK BACKTEST SWEEP — 1 Year                                 ║");
  console.log("╚══════════════════════════════════════════════════════════════════════════════╝");
  console.log("");
  console.log(`  Starting capital: $100,000 | Risk per trade: 0.5% / 1% / 2%\n`);
  console.log(`  ${"CONFIG".padEnd(20)} ${"#".padEnd(4)} ${"W%".padEnd(5)} ${"TOTAL R".padEnd(9)} ${"PF".padEnd(6)} ${"0.5% RISK".padEnd(10)} ${"1% RISK".padEnd(10)} ${"2% RISK".padEnd(10)}`);
  console.log("  " + "─".repeat(80));

  let bestConfig = "";
  let bestR = -Infinity;

  for (const config of SWEEP_CONFIGS) {
    const allTrades: Trade[] = [];
    for (const [date, dd] of dayDataMap) {
      const trades = simulateDay(date, dd.contexts, dd.intradayByTicker, config.overrides);
      allTrades.push(...trades);
    }
    reportConfig(config.name, allTrades);
    const totalR = allTrades.reduce((s, t) => s + t.rMultiple, 0);
    if (totalR > bestR) { bestR = totalR; bestConfig = config.name; }
  }

  console.log("  " + "─".repeat(80));
  console.log(`  BEST: ${bestConfig} → ${bestR >= 0 ? "+" : ""}${bestR.toFixed(2)}R`);

  // ─── Detailed dollar breakdown for top 3 configs ───
  const START = 100_000;
  const riskLevels = [
    { label: "0.5% (conservative)", pct: 0.005 },
    { label: "1% (standard)", pct: 0.01 },
    { label: "2% (aggressive)", pct: 0.02 },
  ];

  // Find top 3 configs by R
  const configResults: { name: string; trades: Trade[]; totalR: number }[] = [];
  for (const config of SWEEP_CONFIGS) {
    const trades: Trade[] = [];
    for (const [date, dd] of dayDataMap) {
      trades.push(...simulateDay(date, dd.contexts, dd.intradayByTicker, config.overrides));
    }
    configResults.push({ name: config.name, trades, totalR: trades.reduce((s, t) => s + t.rMultiple, 0) });
  }
  configResults.sort((a, b) => b.totalR - a.totalR);

  console.log("\n\n╔══════════════════════════════════════════════════════════════════════════════╗");
  console.log("║          DOLLAR P&L — $100,000 Starting Capital (Compounded)               ║");
  console.log("╚══════════════════════════════════════════════════════════════════════════════╝");

  for (const cr of configResults.slice(0, 5)) {
    console.log(`\n  ── ${cr.name} (${cr.trades.length} trades, ${cr.totalR >= 0 ? "+" : ""}${cr.totalR.toFixed(2)}R) ──`);
    for (const rl of riskLevels) {
      const eq = compoundEquity(cr.trades, START, rl.pct);
      const pnl = eq.endEquity - START;
      const retPct = (pnl / START) * 100;
      console.log(`    ${rl.label.padEnd(22)} End: $${eq.endEquity.toLocaleString("en-US", { maximumFractionDigits: 0 }).padEnd(10)} P&L: ${fmtMoney(pnl).padEnd(10)} (${retPct >= 0 ? "+" : ""}${retPct.toFixed(1)}%)  Peak: $${eq.peakEquity.toLocaleString("en-US", { maximumFractionDigits: 0 })}  Low: $${eq.lowEquity.toLocaleString("en-US", { maximumFractionDigits: 0 })}  MaxDD: -$${eq.maxDDDollars.toLocaleString("en-US", { maximumFractionDigits: 0 })}`);
    }
  }
}

main().catch(console.error);
