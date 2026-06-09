import { DEFAULTS } from "@/lib/constants";
import type { Direction } from "@/lib/types";

export interface BreakoutInput {
  bar: { open: number; high: number; low: number; close: number; volume: number };
  rangeHigh: number;
  rangeLow: number;
  vwap: number;
  sma20: number;
  avgBarVolume: number;
}

export interface BreakoutResult {
  direction: Direction;
  entryPrice: number;
  candleQuality: number;
  volumeRatio: number;
  vwapDistance: number;
}

export function checkBreakout(input: BreakoutInput): BreakoutResult | null {
  const { bar, rangeHigh, rangeLow, vwap, sma20, avgBarVolume } = input;
  const candleRange = bar.high - bar.low;
  if (candleRange <= 0) return null;

  const candlePosition = (bar.close - bar.low) / candleRange;
  const volumeRatio = avgBarVolume > 0 ? bar.volume / avgBarVolume : 0;

  if (bar.close > rangeHigh && bar.close > vwap && bar.open > sma20) {
    if (candlePosition < (1 - DEFAULTS.candleQualityThreshold)) return null;
    if (volumeRatio < 1) return null;
    return {
      direction: "LONG",
      entryPrice: bar.close,
      candleQuality: candlePosition,
      volumeRatio,
      vwapDistance: (bar.close - vwap) / vwap,
    };
  }

  if (bar.close < rangeLow && bar.close < vwap && bar.open < sma20) {
    if (candlePosition > DEFAULTS.candleQualityThreshold) return null;
    if (volumeRatio < 1) return null;
    return {
      direction: "SHORT",
      entryPrice: bar.close,
      candleQuality: 1 - candlePosition,
      volumeRatio,
      vwapDistance: (vwap - bar.close) / vwap,
    };
  }

  return null;
}
