import { AlpacaWebSocket } from "@/lib/alpaca/websocket";
import { getCryptoBars } from "@/lib/alpaca/rest";
import { calcEMA } from "@/lib/indicators";
import { TICKERS, TICKER_SHORT, TIMEFRAMES, DEFAULTS } from "@/lib/constants";
import { gatherPreSessionContext } from "./pre-session";
import { RangeBuilder } from "./range-builder";
import { checkBreakout } from "./breakout-detector";
import { calcCompositeScore, selectTrades } from "./ranking";
import { checkExit, calcTrailingStop } from "./exit-tracker";
import { insertRange } from "@/lib/db/queries/ranges";
import { insertSignal, updateSignalOutcome } from "@/lib/db/queries/signals";
import * as alerts from "./alerts";
import type {
  Bar, DailyContext, OpeningRange, Signal, ActiveSignal,
  SessionPhase, Ticker, TickerShort, Timeframe, Grade,
} from "@/lib/types";

interface PendingSignal {
  signal: Signal;
  range: OpeningRange;
  context: DailyContext;
  score: number;
}

export class SessionManager {
  private phase: SessionPhase = "IDLE";
  private ws: AlpacaWebSocket | null = null;
  private contexts: DailyContext[] = [];
  private rangeBuilder: RangeBuilder | null = null;
  private pendingSignals: PendingSignal[] = [];
  private firstBreakoutTime: Date | null = null;
  private selectedSignals: ActiveSignal[] = [];
  private skippedReasons: { ticker: string; reason: string }[] = [];
  private date: string = "";
  private vwapAccumulators: Map<string, { cumVP: number; cumVol: number }> = new Map();
  private barHistory: Map<string, number[]> = new Map();
  private avgBarVolumes: Map<string, number> = new Map();

  async runSession(): Promise<void> {
    this.date = new Date().toISOString().split("T")[0];
    console.log(`[session] Starting ORB session for ${this.date}`);

    try {
      await this.preSession();
      await this.connectAndMonitor();
    } catch (err) {
      console.error("[session] Error:", err);
    } finally {
      this.cleanup();
    }
  }

  private async preSession(): Promise<void> {
    this.phase = "PRE_SESSION";
    console.log("[session] Phase 1: Pre-session context");

    this.contexts = await gatherPreSessionContext();
    if (this.contexts.length === 0) {
      throw new Error("No context data available for any ticker");
    }

    for (const ticker of TICKERS) {
      for (const tf of TIMEFRAMES) {
        const key = `${TICKER_SHORT[ticker]}-${tf}`;
        const avgVol = await this.fetchAvgVolume(ticker, tf);
        this.avgBarVolumes.set(key, avgVol);
      }
    }

    await alerts.alertSessionStart(this.contexts);
    console.log(`[session] Context gathered for ${this.contexts.map(c => c.ticker).join(", ")}`);
  }

  private async fetchAvgVolume(ticker: Ticker, timeframe: Timeframe): Promise<number> {
    try {
      const start = new Date();
      start.setDate(start.getDate() - 14);
      const bars = await getCryptoBars(ticker, `${timeframe}Min`, start.toISOString());
      if (bars.length === 0) return 0;
      const firstBars = bars.filter((_b, i) => i % (390 / timeframe) === 0).slice(0, 10);
      return firstBars.reduce((s, b) => s + b.v, 0) / Math.max(firstBars.length, 1);
    } catch {
      return 0;
    }
  }

  private async connectAndMonitor(): Promise<void> {
    return new Promise((resolve) => {
      this.ws = new AlpacaWebSocket();

      this.ws.on("ready", () => {
        this.phase = "BUILDING_RANGES";
        console.log("[session] Phase 2: Building ranges");

        this.rangeBuilder = new RangeBuilder(this.contexts, this.avgBarVolumes);

        for (const ticker of TICKERS) {
          this.vwapAccumulators.set(TICKER_SHORT[ticker], { cumVP: 0, cumVol: 0 });
          this.barHistory.set(TICKER_SHORT[ticker], []);
        }
      });

      this.ws.on("bar", async (bar: Bar) => {
        try {
          await this.processBar(bar);
        } catch (err) {
          console.error("[session] Bar processing error:", err);
        }
      });

      const eodTimeout = this.scheduleEOD(resolve);

      this.ws.on("close", () => {
        clearTimeout(eodTimeout);
        resolve();
      });

      this.ws.connect();
    });
  }

  private async processBar(bar: Bar): Promise<void> {
    const ticker = TICKER_SHORT[bar.symbol as Ticker];
    if (!ticker) return;

    this.updateVWAP(ticker, bar);
    this.updateBarHistory(ticker, bar);

    if (this.phase === "BUILDING_RANGES" && this.rangeBuilder) {
      const range = this.rangeBuilder.processBar(bar);
      if (range) {
        const ctx = this.contexts.find(c => c.ticker === range.ticker)!;
        await this.onRangeLocked(range, ctx);

        if (this.rangeBuilder.isComplete()) {
          this.phase = "MONITORING";
          console.log("[session] Phase 4: Monitoring for breakouts");
        }
      }
    }

    if (this.phase === "MONITORING") {
      await this.checkForBreakouts(bar);
    }

    if (this.phase === "TRACKING") {
      await this.trackExits(bar);
    }
  }

  private async onRangeLocked(range: OpeningRange, ctx: DailyContext): Promise<void> {
    insertRange({
      ticker: range.ticker,
      date: this.date,
      timeframe: range.timeframe,
      range_high: range.rangeHigh,
      range_low: range.rangeLow,
      range_width: range.rangeWidth,
      open_price: range.openPrice,
      close_price: range.closePrice,
      volume: range.volume,
      vwap_at_close: range.vwapAtClose,
      atr_14: ctx.atr14,
      sma_20: ctx.sma20,
      sma_slope: ctx.smaSlope,
      prior_day_high: ctx.priorDayHigh,
      prior_day_low: ctx.priorDayLow,
      prior_day_close: ctx.priorDayClose,
      premarket_price: ctx.premarketPrice,
      gap_pct: ctx.gapPct,
      gap_direction: ctx.gapDirection,
      quality_grade: range.grade,
      skip_reason: range.skipReason,
    });

    if (range.grade === "SKIP") {
      this.skippedReasons.push({ ticker: range.ticker, reason: range.skipReason! });
    }

    await alerts.alertRangeSet(range, ctx);
  }

  private async checkForBreakouts(bar: Bar): Promise<void> {
    const now = new Date();
    const etHour = now.getUTCHours() - 4;
    const etMinute = now.getUTCMinutes();
    if (etHour > DEFAULTS.timeCutoffHour ||
      (etHour === DEFAULTS.timeCutoffHour && etMinute >= DEFAULTS.timeCutoffMinute)) {
      await this.commitTrades();
      if (this.selectedSignals.length === 0) {
        await alerts.alertNoTrade(this.skippedReasons);
      }
      this.phase = this.selectedSignals.length > 0 ? "TRACKING" : "CLOSED";
      return;
    }

    const ticker = TICKER_SHORT[bar.symbol as Ticker];
    if (!ticker) return;
    if (!this.rangeBuilder) return;

    const ctx = this.contexts.find(c => c.ticker === ticker);
    if (!ctx) return;

    const vwap = this.getCurrentVWAP(ticker);
    const avgBarVol = this.getAvgBarVolume(ticker);

    for (const tf of TIMEFRAMES) {
      const range = this.rangeBuilder.getRange(ticker, tf);
      if (!range || range.grade === "SKIP") continue;
      if (this.pendingSignals.some(p => p.signal.ticker === ticker && p.signal.timeframe === tf)) continue;

      const result = checkBreakout({
        bar: { open: bar.open, high: bar.high, low: bar.low, close: bar.close, volume: bar.volume },
        rangeHigh: range.rangeHigh,
        rangeLow: range.rangeLow,
        vwap,
        sma20: ctx.sma20,
        avgBarVolume: avgBarVol,
      });

      if (result) {
        const gapAligned = (result.direction === "LONG" && ctx.gapDirection === "UP") ||
          (result.direction === "SHORT" && ctx.gapDirection === "DOWN");
        const slopeDowngrade = Math.abs(ctx.smaSlope) < DEFAULTS.smaDowngradeThreshold;

        const score = calcCompositeScore({
          grade: range.grade as Grade,
          gapAligned,
          smaSlope: ctx.smaSlope,
          direction: result.direction,
          vwapDistance: result.vwapDistance,
          breakoutVolumeRatio: result.volumeRatio,
          candleQuality: result.candleQuality,
          slopeDowngrade,
        });

        const signal: Signal = {
          ticker,
          timeframe: tf,
          direction: result.direction,
          grade: range.grade as Grade,
          entryPrice: result.entryPrice,
          stopPrice: result.direction === "LONG" ? range.rangeLow : range.rangeHigh,
          targetPrice: result.direction === "LONG"
            ? result.entryPrice + range.rangeWidth
            : result.entryPrice - range.rangeWidth,
          risk: result.direction === "LONG"
            ? result.entryPrice - range.rangeLow
            : range.rangeHigh - result.entryPrice,
          vwapAtEntry: vwap,
          breakoutVolumeRatio: result.volumeRatio,
          breakoutCandleQuality: result.candleQuality,
          rankingScore: score.total,
          gapAligned,
          trendAligned: true,
          smaSlope: ctx.smaSlope,
          rangeAtrPct: range.rangeAtrPct,
          gapPct: ctx.gapPct,
          signalTime: bar.timestamp,
        };

        this.pendingSignals.push({ signal, range, context: ctx, score: score.total });

        if (!this.firstBreakoutTime) {
          this.firstBreakoutTime = new Date();
          setTimeout(() => this.commitTrades(), DEFAULTS.selectionDelaySec * 1000);
        }
      }
    }
  }

  private async commitTrades(): Promise<void> {
    if (this.selectedSignals.length > 0) return;

    const candidates = this.pendingSignals.map(p => ({
      id: 0,
      ticker: p.signal.ticker,
      score: p.score,
      grade: p.signal.grade,
    }));

    const selected = selectTrades(candidates);

    for (const sel of selected) {
      const pending = this.pendingSignals.find(p => p.signal.ticker === sel.ticker)!;
      const sig = pending.signal;

      const dbId = insertSignal({
        ticker: sig.ticker,
        date: this.date,
        timeframe: sig.timeframe,
        direction: sig.direction,
        grade: sig.grade,
        range_high: pending.range.rangeHigh,
        range_low: pending.range.rangeLow,
        range_width: pending.range.rangeWidth,
        entry_price: sig.entryPrice,
        stop_price: sig.stopPrice,
        target_price: sig.targetPrice,
        risk: sig.risk,
        signal_time: sig.signalTime.toISOString(),
        vwap_at_entry: sig.vwapAtEntry,
        breakout_volume_ratio: sig.breakoutVolumeRatio,
        breakout_candle_quality: sig.breakoutCandleQuality,
        ranking_score: sig.rankingScore,
        was_selected: 1,
        range_atr_pct: sig.rangeAtrPct,
        gap_pct: sig.gapPct,
        gap_aligned: sig.gapAligned ? 1 : 0,
        trend_aligned: sig.trendAligned ? 1 : 0,
        sma_slope: sig.smaSlope,
      });

      const active: ActiveSignal = {
        ...sig,
        outcome: null,
        exitType: null,
        exitPrice: null,
        exitTime: null,
        rMultiple: null,
        targetHit: false,
        maxFavorable: sig.entryPrice,
        maxAdverse: sig.entryPrice,
      };
      (active as any).dbId = dbId;
      this.selectedSignals.push(active);

      const rank = selected.indexOf(sel) + 1;
      await alerts.alertSignal(sig, rank, selected.length);
    }

    if (this.selectedSignals.length > 0) {
      this.phase = "TRACKING";
      console.log(`[session] Phase 5: Tracking ${this.selectedSignals.length} active signal(s)`);
    }
  }

  private async trackExits(bar: Bar): Promise<void> {
    const ticker = TICKER_SHORT[bar.symbol as Ticker];
    if (!ticker) return;

    for (const signal of this.selectedSignals) {
      if (signal.ticker !== ticker || signal.outcome !== null) continue;

      if (signal.direction === "LONG") {
        signal.maxFavorable = Math.max(signal.maxFavorable, bar.high);
        signal.maxAdverse = Math.min(signal.maxAdverse, bar.low);
      } else {
        signal.maxFavorable = Math.min(signal.maxFavorable, bar.low);
        signal.maxAdverse = Math.max(signal.maxAdverse, bar.high);
      }

      const closes = this.barHistory.get(ticker) ?? [];
      const ema9 = closes.length >= 9 ? calcEMA(closes, 9) : signal.entryPrice;
      const trailingStop = signal.targetHit ? calcTrailingStop(signal.direction, ema9) : null;

      const exitResult = checkExit({
        direction: signal.direction,
        entryPrice: signal.entryPrice,
        stopPrice: signal.stopPrice,
        targetPrice: signal.targetPrice,
        rangeHigh: bar.high,
        rangeLow: bar.low,
        targetHit: signal.targetHit,
        trailingStop,
        bar: { high: bar.high, low: bar.low, close: bar.close, volume: bar.volume },
        entryTime: signal.signalTime,
        now: new Date(),
        ema9,
      });

      if (exitResult) {
        if (exitResult.type === "target" && !signal.targetHit) {
          signal.targetHit = true;
          signal.stopPrice = signal.entryPrice;
          await alerts.alertTargetHit(signal);
          continue;
        }

        const pnl = signal.direction === "LONG"
          ? exitResult.price - signal.entryPrice
          : signal.entryPrice - exitResult.price;
        const rMultiple = signal.risk > 0 ? pnl / signal.risk : 0;

        signal.outcome = pnl > signal.risk * 0.2 ? "WIN" :
          pnl < -signal.risk * 0.2 ? "LOSS" : "SCRATCH";
        signal.exitType = exitResult.type;
        signal.exitPrice = exitResult.price;
        signal.exitTime = new Date();
        signal.rMultiple = rMultiple;

        updateSignalOutcome((signal as any).dbId, {
          outcome: signal.outcome,
          exit_type: signal.exitType,
          exit_price: signal.exitPrice,
          exit_time: signal.exitTime.toISOString(),
          r_multiple: signal.rMultiple,
          target_hit: signal.targetHit ? 1 : 0,
          max_favorable: signal.maxFavorable,
          max_adverse: signal.maxAdverse,
        });

        await alerts.alertTradeClose(signal);
      }
    }

    if (this.selectedSignals.every(s => s.outcome !== null)) {
      this.phase = "CLOSED";
      console.log("[session] All trades closed. Session complete.");
    }
  }

  private scheduleEOD(resolve: () => void): NodeJS.Timeout {
    const now = new Date();
    const eod = new Date(now);
    eod.setUTCHours(20, 0, 0, 0);
    const msUntilEOD = Math.max(0, eod.getTime() - now.getTime());

    return setTimeout(async () => {
      console.log("[session] End of day — closing all open signals");

      for (const signal of this.selectedSignals) {
        if (signal.outcome !== null) continue;
        signal.outcome = "SCRATCH";
        signal.exitType = "eod";
        signal.exitPrice = signal.maxFavorable;
        signal.exitTime = new Date();
        signal.rMultiple = 0;

        updateSignalOutcome((signal as any).dbId, {
          outcome: "SCRATCH",
          exit_type: "eod",
          exit_price: signal.exitPrice,
          exit_time: signal.exitTime.toISOString(),
          r_multiple: 0,
          target_hit: signal.targetHit ? 1 : 0,
          max_favorable: signal.maxFavorable,
          max_adverse: signal.maxAdverse,
        });
      }

      const stats = { winRate: 0, wins: 0, losses: 0 };
      const completed = this.selectedSignals.filter(s => s.outcome);
      if (completed.length > 0) {
        stats.wins = completed.filter(s => s.outcome === "WIN").length;
        stats.losses = completed.filter(s => s.outcome === "LOSS").length;
        stats.winRate = (stats.wins / completed.length) * 100;
      }

      await alerts.alertDailySummary(this.selectedSignals, this.skippedReasons, stats);
      this.phase = "CLOSED";
      this.cleanup();
      resolve();
    }, msUntilEOD);
  }

  private updateVWAP(ticker: string, bar: Bar): void {
    const acc = this.vwapAccumulators.get(ticker);
    if (!acc) return;
    const typical = (bar.high + bar.low + bar.close) / 3;
    acc.cumVP += typical * bar.volume;
    acc.cumVol += bar.volume;
  }

  private getCurrentVWAP(ticker: string): number {
    const acc = this.vwapAccumulators.get(ticker);
    if (!acc || acc.cumVol === 0) return 0;
    return acc.cumVP / acc.cumVol;
  }

  private updateBarHistory(ticker: string, bar: Bar): void {
    const hist = this.barHistory.get(ticker);
    if (hist) hist.push(bar.close);
  }

  private getAvgBarVolume(ticker: string): number {
    const hist = this.barHistory.get(ticker);
    if (!hist || hist.length < 2) return 0;
    return hist.length;
  }

  private cleanup(): void {
    this.ws?.disconnect();
    this.ws = null;
  }
}
