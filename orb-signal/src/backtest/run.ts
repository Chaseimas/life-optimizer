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
const BT_TICKERS = ["BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD"];
const BT_SHORT: Record<string, string> = {
  "BTC/USD": "BTC", "ETH/USD": "ETH", "SOL/USD": "SOL", "XRP/USD": "XRP",
};
const TIMEFRAMES = [5, 10, 15] as const;
const START_DATE = "2026-02-08";
const END_DATE = "2026-06-08";
const CONTEXT_START = "2025-12-01"; // extra lookback for SMA20/ATR14

const DEFAULTS = {
  maxRangeAtrPct: 75,
  smaDowngradeThreshold: 0.5,
  smaSlopSkipThreshold: 0.2,
  candleQualityThreshold: 0.3,
  minVolumeRatio: 0.5,
  timeCutoffBars: 120, // 11:30 AM = 120 bars after 9:30
  timeExitMinutes: 120,
  maxTradesPerDay: 3,
  secondTradeScoreGap: 2,
  selectionDelayBars: 2,
};

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
// DATA FETCHING
// ═══════════════════════════════════════════════════════════════
function headers() {
  return {
    "APCA-API-KEY-ID": process.env.ALPACA_API_KEY!,
    "APCA-API-SECRET-KEY": process.env.ALPACA_API_SECRET!,
  };
}

async function fetchAllBars(symbol: string, timeframe: string, start: string, end: string): Promise<AlpacaBar[]> {
  const allBars: AlpacaBar[] = [];
  let pageToken: string | null = null;
  let pages = 0;

  do {
    const params = new URLSearchParams({
      symbols: symbol, timeframe, start, end, limit: "10000", sort: "asc",
    });
    if (pageToken) params.set("page_token", pageToken);

    const url = `${ALPACA_REST_URL}/v1beta3/crypto/us/bars?${params}`;
    const res = await fetch(url, { headers: headers() });
    if (!res.ok) throw new Error(`Alpaca ${res.status}: ${await res.text()}`);

    const data = await res.json();
    const bars: AlpacaBar[] = data.bars?.[symbol] ?? [];
    allBars.push(...bars);
    pageToken = data.next_page_token ?? null;
    pages++;
    if (pageToken) await new Promise(r => setTimeout(r, 200));
  } while (pageToken);

  return allBars;
}

// ═══════════════════════════════════════════════════════════════
// TIME HELPERS
// ═══════════════════════════════════════════════════════════════
function etOffset(d: Date): number {
  // US DST 2026: Mar 8 → Nov 1
  const m = d.getUTCMonth(), day = d.getUTCDate();
  if (m < 2 || m > 10) return 5;       // Jan/Feb/Dec = EST
  if (m > 2 && m < 10) return 4;       // Apr–Oct = EDT
  if (m === 2) return day >= 8 ? 4 : 5; // Mar: DST starts 8th
  return day < 1 ? 4 : 5;              // Nov: DST ends 1st
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
// DAILY CONTEXT
// ═══════════════════════════════════════════════════════════════
function computeContext(
  shortTicker: string,
  dailyBars: AlpacaBar[],
  dayIdx: number,
  openPrice: number,
): DayContext | null {
  if (dayIdx < 20) return null;
  const prior = dailyBars.slice(Math.max(0, dayIdx - 40), dayIdx);
  if (prior.length < 15) return null;

  const closes = prior.map(b => b.c);
  const sma20 = calcSMA(closes, 20);
  if (isNaN(sma20)) return null;

  const hlc = prior.map(b => ({ high: b.h, low: b.l, close: b.c }));
  const atr14 = calcATR(hlc, 14);
  if (atr14 <= 0) return null;

  // SMA slope from last 5 SMA values
  const smaVals: number[] = [];
  for (let i = Math.max(5, closes.length - 5); i <= closes.length; i++) {
    const sl = closes.slice(0, i);
    if (sl.length >= 20) smaVals.push(calcSMA(sl, 20));
  }
  const smaSlope = smaVals.length >= 2 ? calcSMASlope(smaVals) : 0;

  const priorClose = dailyBars[dayIdx - 1].c;
  const gapPct = ((openPrice - priorClose) / priorClose) * 100;
  const gapDir = gapPct > 0.1 ? "UP" as const : gapPct < -0.1 ? "DOWN" as const : "FLAT" as const;

  return {
    ticker: shortTicker,
    sma20, atr14, smaSlope,
    priorClose, openPrice,
    gapPct, gapDirection: gapDir,
  };
}

// ═══════════════════════════════════════════════════════════════
// DAY SIMULATION
// ═══════════════════════════════════════════════════════════════
function simulateDay(
  date: string,
  contexts: DayContext[],
  intradayByTicker: Map<string, AlpacaBar[]>,
): Trade[] {
  // ─── Build opening ranges ───
  interface RangeInfo {
    ticker: string; timeframe: number;
    rangeHigh: number; rangeLow: number; rangeWidth: number;
    volume: number; grade: string; skipReason: string | null;
    rangeAtrPct: number; slopeDowngrade: boolean;
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

      const q = gradeRange({
        rangeWidth, atr14: ctx.atr14,
        volume: vol, avgVolume: avgVol,
        smaSlope: ctx.smaSlope,
      });

      ranges.push({
        ticker: ctx.ticker, timeframe: tf,
        rangeHigh, rangeLow, rangeWidth, volume: vol,
        grade: q.grade, skipReason: q.skipReason,
        rangeAtrPct: q.rangeAtrPct, slopeDowngrade: q.slopeDowngrade,
      });
    }
  }

  // ─── Monitor for breakouts ───
  interface Pending {
    ticker: string; timeframe: number; direction: Direction; grade: Grade;
    entryPrice: number; stopPrice: number; targetPrice: number; risk: number;
    score: number; breakoutBar: number;
    rangeHigh: number; rangeLow: number; rangeWidth: number;
    gapAligned: boolean; smaSlope: number; rangeAtrPct: number; gapPct: number;
  }

  const pending: Pending[] = [];
  let firstBkBar: number | null = null;
  const detected = new Set<string>();

  // Running VWAP accumulators
  const vwapAcc = new Map<string, { vp: number; vol: number }>();
  for (const ctx of contexts) vwapAcc.set(ctx.ticker, { vp: 0, vol: 0 });

  const maxLen = Math.max(...Array.from(intradayByTicker.values()).map(b => b.length), 0);

  // Accumulate VWAP for range-building bars (0..15)
  for (const [tk, bars] of intradayByTicker) {
    for (let i = 0; i < Math.min(16, bars.length); i++) {
      const b = bars[i];
      const a = vwapAcc.get(tk)!;
      if (a) {
        a.vp += ((b.h + b.l + b.c) / 3) * b.v;
        a.vol += b.v;
      }
    }
  }

  // Scan from bar 16 to cutoff
  for (let bi = 16; bi < Math.min(maxLen, DEFAULTS.timeCutoffBars); bi++) {
    // Update VWAP
    for (const [tk, bars] of intradayByTicker) {
      if (bi >= bars.length) continue;
      const b = bars[bi];
      const a = vwapAcc.get(tk);
      if (a) {
        a.vp += ((b.h + b.l + b.c) / 3) * b.v;
        a.vol += b.v;
      }
    }

    // Check each range for breakout
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
        const gapAligned = (bo.direction === "LONG" && ctx.gapDirection === "UP") ||
          (bo.direction === "SHORT" && ctx.gapDirection === "DOWN");
        const slopeDown = Math.abs(ctx.smaSlope) < DEFAULTS.smaDowngradeThreshold;

        const cs = calcCompositeScore({
          grade: rng.grade as Grade, gapAligned,
          smaSlope: ctx.smaSlope, direction: bo.direction,
          vwapDistance: bo.vwapDistance, breakoutVolumeRatio: bo.volumeRatio,
          candleQuality: bo.candleQuality, slopeDowngrade: slopeDown,
        });

        const stop = bo.direction === "LONG" ? rng.rangeLow : rng.rangeHigh;
        const target = bo.direction === "LONG"
          ? bo.entryPrice + rng.rangeWidth
          : bo.entryPrice - rng.rangeWidth;
        const risk = bo.direction === "LONG"
          ? bo.entryPrice - rng.rangeLow
          : rng.rangeHigh - bo.entryPrice;

        if (risk <= 0) continue;

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

    if (firstBkBar !== null && bi >= firstBkBar + DEFAULTS.selectionDelayBars) break;
  }

  if (pending.length === 0) return [];

  // ─── Select trades ───
  const cands = pending.map((p, i) => ({
    id: i, ticker: p.ticker, score: p.score, grade: p.grade,
  }));
  const selected = selectTrades(cands);

  // ─── Track exits ───
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

    for (let i = p.breakoutBar + 1; i < bars.length; i++) {
      const b = bars[i];
      closeHist.push(b.c);

      const ema9 = closeHist.length >= 9 ? calcEMA(closeHist, 9) : p.entryPrice;
      const trail = targetHit ? calcTrailingStop(p.direction, ema9) : null;

      const ex = checkExit({
        direction: p.direction,
        entryPrice: p.entryPrice,
        stopPrice: curStop,
        targetPrice: p.targetPrice,
        rangeHigh: p.rangeHigh,
        rangeLow: p.rangeLow,
        targetHit, trailingStop: trail,
        bar: { high: b.h, low: b.l, close: b.c, volume: b.v },
        entryTime: new Date(bars[p.breakoutBar].t),
        now: new Date(b.t),
        ema9,
      });

      if (ex) {
        if (ex.type === "target" && !targetHit) {
          targetHit = true;
          curStop = p.entryPrice; // move stop to breakeven
          continue;
        }
        exitPrice = ex.price;
        exitType = ex.type;
        break;
      }
    }

    const pnl = p.direction === "LONG" ? exitPrice - p.entryPrice : p.entryPrice - exitPrice;
    const rMul = p.risk > 0 ? pnl / p.risk : 0;
    const outcome = pnl > p.risk * 0.2 ? "WIN" as const
      : pnl < -p.risk * 0.2 ? "LOSS" as const : "SCRATCH" as const;

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
// REPORT
// ═══════════════════════════════════════════════════════════════
function printReport(allTrades: Trade[], tradingDays: number) {
  const W = allTrades.filter(t => t.outcome === "WIN");
  const L = allTrades.filter(t => t.outcome === "LOSS");
  const S = allTrades.filter(t => t.outcome === "SCRATCH");
  const totalR = allTrades.reduce((s, t) => s + t.rMultiple, 0);
  const avgR = allTrades.length > 0 ? totalR / allTrades.length : 0;
  const winRate = allTrades.length > 0 ? (W.length / allTrades.length) * 100 : 0;
  const daysWithTrades = new Set(allTrades.map(t => t.date)).size;

  // Profit factor
  const grossWin = W.reduce((s, t) => s + t.rMultiple, 0);
  const grossLoss = Math.abs(L.reduce((s, t) => s + t.rMultiple, 0));
  const pf = grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? Infinity : 0;

  // Max drawdown
  let peak = 0, dd = 0, maxDD = 0;
  let cumR = 0;
  const sorted = [...allTrades].sort((a, b) => a.date.localeCompare(b.date));
  for (const t of sorted) {
    cumR += t.rMultiple;
    if (cumR > peak) peak = cumR;
    dd = peak - cumR;
    if (dd > maxDD) maxDD = dd;
  }

  // Best/worst
  const best = allTrades.length > 0 ? allTrades.reduce((a, b) => a.rMultiple > b.rMultiple ? a : b) : null;
  const worst = allTrades.length > 0 ? allTrades.reduce((a, b) => a.rMultiple < b.rMultiple ? a : b) : null;

  console.log("");
  console.log("╔══════════════════════════════════════════════════════════════╗");
  console.log("║          ORB BACKTEST — Feb 8 to Jun 8, 2026                ║");
  console.log("║          BTC · ETH · SOL · XRP  |  5/10/15 min             ║");
  console.log("╚══════════════════════════════════════════════════════════════╝");
  console.log("");

  console.log("OVERALL PERFORMANCE");
  console.log("─".repeat(60));
  console.log(`  Trading days:     ${tradingDays}`);
  console.log(`  Days with trades: ${daysWithTrades}`);
  console.log(`  Total trades:     ${allTrades.length}`);
  console.log("");
  console.log(`  Win Rate:    ${winRate.toFixed(1)}%  (${W.length}W - ${L.length}L - ${S.length}S)`);
  console.log(`  Avg R:       ${avgR >= 0 ? "+" : ""}${avgR.toFixed(2)}R`);
  console.log(`  Total R:     ${totalR >= 0 ? "+" : ""}${totalR.toFixed(2)}R`);
  console.log(`  Profit Factor: ${pf === Infinity ? "∞" : pf.toFixed(2)}x`);
  console.log(`  Max Drawdown:  -${maxDD.toFixed(2)}R`);
  if (best) console.log(`  Best trade:  +${best.rMultiple.toFixed(2)}R (${best.ticker} ${best.direction} ${best.timeframe}m, ${best.date})`);
  if (worst) console.log(`  Worst trade: ${worst.rMultiple.toFixed(2)}R (${worst.ticker} ${worst.direction} ${worst.timeframe}m, ${worst.date})`);
  console.log("");

  // By ticker
  console.log("BY TICKER");
  console.log("─".repeat(60));
  console.log("  Ticker   Trades   Win%      Avg R     Total R");
  for (const tk of ["BTC", "ETH", "SOL", "XRP"]) {
    const tt = allTrades.filter(t => t.ticker === tk);
    if (tt.length === 0) { console.log(`  ${tk.padEnd(8)} 0`); continue; }
    const w = tt.filter(t => t.outcome === "WIN").length;
    const wr = (w / tt.length * 100).toFixed(1);
    const ar = (tt.reduce((s, t) => s + t.rMultiple, 0) / tt.length).toFixed(2);
    const tr = tt.reduce((s, t) => s + t.rMultiple, 0).toFixed(2);
    console.log(`  ${tk.padEnd(8)} ${String(tt.length).padEnd(8)} ${(wr + "%").padEnd(9)} ${(Number(ar) >= 0 ? "+" : "") + ar + "R".padEnd(1)}    ${(Number(tr) >= 0 ? "+" : "") + tr}R`);
  }
  console.log("");

  // By timeframe
  console.log("BY TIMEFRAME");
  console.log("─".repeat(60));
  console.log("  TF      Trades   Win%      Avg R     Total R");
  for (const tf of [5, 10, 15]) {
    const tt = allTrades.filter(t => t.timeframe === tf);
    if (tt.length === 0) { console.log(`  ${tf}m`.padEnd(9) + " 0"); continue; }
    const w = tt.filter(t => t.outcome === "WIN").length;
    const wr = (w / tt.length * 100).toFixed(1);
    const ar = (tt.reduce((s, t) => s + t.rMultiple, 0) / tt.length).toFixed(2);
    const tr = tt.reduce((s, t) => s + t.rMultiple, 0).toFixed(2);
    console.log(`  ${(tf + "m").padEnd(8)} ${String(tt.length).padEnd(8)} ${(wr + "%").padEnd(9)} ${(Number(ar) >= 0 ? "+" : "") + ar + "R"}    ${(Number(tr) >= 0 ? "+" : "") + tr}R`);
  }
  console.log("");

  // By grade
  console.log("BY GRADE");
  console.log("─".repeat(60));
  console.log("  Grade   Trades   Win%      Avg R");
  for (const g of ["A", "B", "C"]) {
    const tt = allTrades.filter(t => t.grade === g);
    if (tt.length === 0) continue;
    const w = tt.filter(t => t.outcome === "WIN").length;
    const wr = (w / tt.length * 100).toFixed(1);
    const ar = (tt.reduce((s, t) => s + t.rMultiple, 0) / tt.length).toFixed(2);
    console.log(`  ${g.padEnd(8)} ${String(tt.length).padEnd(8)} ${(wr + "%").padEnd(9)} ${(Number(ar) >= 0 ? "+" : "") + ar}R`);
  }
  console.log("");

  // By exit type
  console.log("BY EXIT TYPE");
  console.log("─".repeat(60));
  console.log("  Type      Count    Avg R");
  for (const et of ["target", "trail", "stop", "failure", "time", "eod"]) {
    const tt = allTrades.filter(t => t.exitType === et);
    if (tt.length === 0) continue;
    const ar = (tt.reduce((s, t) => s + t.rMultiple, 0) / tt.length).toFixed(2);
    console.log(`  ${et.padEnd(10)} ${String(tt.length).padEnd(8)} ${(Number(ar) >= 0 ? "+" : "") + ar}R`);
  }
  console.log("");

  // By direction
  console.log("BY DIRECTION");
  console.log("─".repeat(60));
  console.log("  Dir     Trades   Win%      Avg R     Total R");
  for (const dir of ["LONG", "SHORT"] as const) {
    const tt = allTrades.filter(t => t.direction === dir);
    if (tt.length === 0) { console.log(`  ${dir.padEnd(8)} 0`); continue; }
    const w = tt.filter(t => t.outcome === "WIN").length;
    const wr = (w / tt.length * 100).toFixed(1);
    const ar = (tt.reduce((s, t) => s + t.rMultiple, 0) / tt.length).toFixed(2);
    const tr = tt.reduce((s, t) => s + t.rMultiple, 0).toFixed(2);
    console.log(`  ${dir.padEnd(8)} ${String(tt.length).padEnd(8)} ${(wr + "%").padEnd(9)} ${(Number(ar) >= 0 ? "+" : "") + ar}R    ${(Number(tr) >= 0 ? "+" : "") + tr}R`);
  }
  console.log("");

  // Monthly breakdown
  console.log("MONTHLY");
  console.log("─".repeat(60));
  console.log("  Month        Trades   Win%      Total R");
  const months = ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06"];
  for (const mo of months) {
    const tt = allTrades.filter(t => t.date.startsWith(mo));
    if (tt.length === 0) { console.log(`  ${mo.padEnd(13)} 0`); continue; }
    const w = tt.filter(t => t.outcome === "WIN").length;
    const wr = (w / tt.length * 100).toFixed(1);
    const tr = tt.reduce((s, t) => s + t.rMultiple, 0).toFixed(2);
    console.log(`  ${mo.padEnd(13)} ${String(tt.length).padEnd(8)} ${(wr + "%").padEnd(9)} ${(Number(tr) >= 0 ? "+" : "") + tr}R`);
  }
  console.log("");

  // Equity curve (simple ASCII)
  console.log("EQUITY CURVE (cumulative R)");
  console.log("─".repeat(60));
  const eqPoints: number[] = [0];
  for (const t of sorted) eqPoints.push(eqPoints[eqPoints.length - 1] + t.rMultiple);
  const eqMin = Math.min(...eqPoints);
  const eqMax = Math.max(...eqPoints);
  const eqRange = eqMax - eqMin || 1;
  const width = 50;
  const step = Math.max(1, Math.floor(eqPoints.length / 20));
  for (let i = 0; i < eqPoints.length; i += step) {
    const val = eqPoints[i];
    const pos = Math.round(((val - eqMin) / eqRange) * width);
    const bar = "█".repeat(Math.max(0, pos)) + "░".repeat(Math.max(0, width - pos));
    const label = i === 0 ? "START" : sorted[i - 1]?.date.slice(5) ?? "";
    console.log(`  ${label.padEnd(6)} ${bar} ${val >= 0 ? "+" : ""}${val.toFixed(1)}R`);
  }
  // Always show final
  const finalR = eqPoints[eqPoints.length - 1];
  const finalPos = Math.round(((finalR - eqMin) / eqRange) * width);
  const finalBar = "█".repeat(Math.max(0, finalPos)) + "░".repeat(Math.max(0, width - finalPos));
  console.log(`  ${"END".padEnd(6)} ${finalBar} ${finalR >= 0 ? "+" : ""}${finalR.toFixed(1)}R`);
  console.log("");

  // Full trade log
  console.log("TRADE LOG");
  console.log("─".repeat(92));
  console.log("  Date        Ticker  TF   Dir    Grade  Entry          Exit           R       Type");
  console.log("  " + "─".repeat(88));
  for (const t of sorted) {
    const rStr = (t.rMultiple >= 0 ? "+" : "") + t.rMultiple.toFixed(2) + "R";
    console.log(
      `  ${t.date}  ${t.ticker.padEnd(6)}  ${(t.timeframe + "m").padEnd(4)} ${t.direction.padEnd(6)} ${t.grade.padEnd(6)}` +
      ` $${t.entryPrice.toFixed(2).padStart(12)}  $${t.exitPrice.toFixed(2).padStart(12)}  ${rStr.padStart(7)}  ${t.exitType}`
    );
  }
  console.log("");
  console.log(`  Total: ${totalR >= 0 ? "+" : ""}${totalR.toFixed(2)}R across ${allTrades.length} trades over ${tradingDays} trading days`);
  console.log("");
}

// ═══════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════
async function main() {
  console.log("[backtest] ORB Backtest starting...");
  console.log(`[backtest] Period: ${START_DATE} → ${END_DATE}`);
  console.log(`[backtest] Tickers: ${BT_TICKERS.map(t => BT_SHORT[t]).join(", ")}`);
  console.log("");

  if (!process.env.ALPACA_API_KEY || !process.env.ALPACA_API_SECRET) {
    console.error("ERROR: Set ALPACA_API_KEY and ALPACA_API_SECRET in .env.local");
    process.exit(1);
  }

  // ─── Fetch daily bars ───
  console.log("[backtest] Fetching daily bars...");
  const dailyByTicker = new Map<string, AlpacaBar[]>();
  for (const ticker of BT_TICKERS) {
    const short = BT_SHORT[ticker];
    process.stdout.write(`  ${short}... `);
    const bars = await fetchAllBars(ticker, "1Day", CONTEXT_START, END_DATE);
    dailyByTicker.set(ticker, bars);
    console.log(`${bars.length} bars`);
    await new Promise(r => setTimeout(r, 300));
  }

  // ─── Fetch 1-min intraday bars ───
  console.log("[backtest] Fetching 1-min intraday bars (this may take a minute)...");
  const intradayByTicker = new Map<string, AlpacaBar[]>();
  for (const ticker of BT_TICKERS) {
    const short = BT_SHORT[ticker];
    process.stdout.write(`  ${short}... `);
    const bars = await fetchAllBars(ticker, "1Min", START_DATE + "T00:00:00Z", END_DATE + "T23:59:59Z");
    intradayByTicker.set(ticker, bars);
    console.log(`${bars.length} bars (${Math.ceil(bars.length / 1440)} days)`);
    await new Promise(r => setTimeout(r, 300));
  }

  // ─── Group intraday bars by date & filter to market hours ───
  console.log("[backtest] Processing intraday data...");
  // Map: ticker → date → sorted bars
  const dayBarsMap = new Map<string, Map<string, AlpacaBar[]>>();
  for (const [ticker, bars] of intradayByTicker) {
    const short = BT_SHORT[ticker];
    const byDate = new Map<string, AlpacaBar[]>();
    for (const bar of bars) {
      if (!isMarketHours(bar)) continue;
      const d = barDateET(bar);
      if (!byDate.has(d)) byDate.set(d, []);
      byDate.get(d)!.push(bar);
    }
    dayBarsMap.set(short, byDate);
  }

  // Build daily bar date index
  const dailyDateIdx = new Map<string, Map<string, number>>();
  for (const [ticker, bars] of dailyByTicker) {
    const short = BT_SHORT[ticker];
    const idx = new Map<string, number>();
    for (let i = 0; i < bars.length; i++) {
      idx.set(bars[i].t.split("T")[0], i);
    }
    dailyDateIdx.set(short, idx);
  }

  // ─── Run simulation ───
  const tradingDays = getTradingDays(START_DATE, END_DATE);
  console.log(`[backtest] Simulating ${tradingDays.length} trading days...`);

  const allTrades: Trade[] = [];
  let daysProcessed = 0;
  let daysSkipped = 0;

  for (const date of tradingDays) {
    // Build contexts for each ticker
    const contexts: DayContext[] = [];
    const dayIntraday = new Map<string, AlpacaBar[]>();

    for (const ticker of BT_TICKERS) {
      const short = BT_SHORT[ticker];
      const dailyBars = dailyByTicker.get(ticker)!;
      const dateIndex = dailyDateIdx.get(short)?.get(date);
      if (dateIndex === undefined) continue;

      const bars = dayBarsMap.get(short)?.get(date);
      if (!bars || bars.length < 20) continue;

      const openPrice = bars[0].o;
      const ctx = computeContext(short, dailyBars, dateIndex, openPrice);
      if (!ctx) continue;

      contexts.push(ctx);
      dayIntraday.set(short, bars);
    }

    if (contexts.length === 0) {
      daysSkipped++;
      continue;
    }

    const dayTrades = simulateDay(date, contexts, dayIntraday);
    allTrades.push(...dayTrades);
    daysProcessed++;

    // Progress
    if (daysProcessed % 10 === 0) {
      console.log(`  [${daysProcessed}/${tradingDays.length}] ${date} — ${allTrades.length} trades so far`);
    }
  }

  console.log(`[backtest] Done. ${daysProcessed} days processed, ${daysSkipped} skipped (no data).`);
  console.log("");

  printReport(allTrades, tradingDays.length);
}

main().catch(err => {
  console.error("[backtest] Fatal error:", err);
  process.exit(1);
});
