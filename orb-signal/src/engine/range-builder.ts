import { TIMEFRAMES, TICKER_SHORT } from "@/lib/constants";
import { calcVWAP } from "@/lib/indicators";
import { gradeRange } from "./quality-gate";
import type { Bar, Ticker, TickerShort, Timeframe, OpeningRange, DailyContext } from "@/lib/types";

interface RangeBuild {
  ticker: TickerShort;
  timeframe: Timeframe;
  bars: { high: number; low: number; close: number; volume: number; open: number }[];
  barsNeeded: number;
  locked: boolean;
  range: OpeningRange | null;
}

export class RangeBuilder {
  private builds: Map<string, RangeBuild> = new Map();
  private sessionStart: Date;
  private contexts: Map<string, DailyContext> = new Map();
  private avgVolumes: Map<string, number> = new Map();

  constructor(contexts: DailyContext[], avgVolumes: Map<string, number>) {
    this.sessionStart = new Date();
    for (const ctx of contexts) {
      this.contexts.set(ctx.ticker, ctx);
    }
    this.avgVolumes = avgVolumes;

    for (const ctx of contexts) {
      for (const tf of TIMEFRAMES) {
        const key = `${ctx.ticker}-${tf}`;
        this.builds.set(key, {
          ticker: ctx.ticker,
          timeframe: tf,
          bars: [],
          barsNeeded: tf,
          locked: false,
          range: null,
        });
      }
    }
  }

  processBar(bar: Bar): OpeningRange | null {
    const ticker = TICKER_SHORT[bar.symbol as Ticker];
    if (!ticker) return null;

    for (const tf of TIMEFRAMES) {
      const key = `${ticker}-${tf}`;
      const build = this.builds.get(key);
      if (!build || build.locked) continue;

      build.bars.push({
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: bar.volume,
        open: bar.open,
      });

      if (build.bars.length >= build.barsNeeded) {
        build.locked = true;
        build.range = this.lockRange(build);
        return build.range;
      }
    }
    return null;
  }

  private lockRange(build: RangeBuild): OpeningRange {
    const ctx = this.contexts.get(build.ticker)!;
    const rangeHigh = Math.max(...build.bars.map(b => b.high));
    const rangeLow = Math.min(...build.bars.map(b => b.low));
    const rangeWidth = rangeHigh - rangeLow;
    const volume = build.bars.reduce((s, b) => s + b.volume, 0);
    const vwapBars = build.bars.map(b => ({
      high: b.high, low: b.low, close: b.close, volume: b.volume,
    }));
    const vwap = calcVWAP(vwapBars);
    const avgVol = this.avgVolumes.get(`${build.ticker}-${build.timeframe}`) ?? volume;

    const quality = gradeRange({
      rangeWidth,
      atr14: ctx.atr14,
      volume,
      avgVolume: avgVol,
      smaSlope: ctx.smaSlope,
    });

    return {
      ticker: build.ticker,
      timeframe: build.timeframe,
      rangeHigh,
      rangeLow,
      rangeWidth,
      openPrice: build.bars[0].open,
      closePrice: build.bars[build.bars.length - 1].close,
      volume,
      vwapAtClose: vwap,
      grade: quality.grade,
      skipReason: quality.skipReason,
      rangeAtrPct: quality.rangeAtrPct,
    };
  }

  getRange(ticker: TickerShort, timeframe: Timeframe): OpeningRange | null {
    return this.builds.get(`${ticker}-${timeframe}`)?.range ?? null;
  }

  getAllRanges(): OpeningRange[] {
    return Array.from(this.builds.values())
      .filter(b => b.range !== null)
      .map(b => b.range!);
  }

  isComplete(): boolean {
    return Array.from(this.builds.values()).every(b => b.locked);
  }
}
