import { DEFAULTS } from "@/lib/constants";
import type { Direction, ExitType } from "@/lib/types";

export interface ExitInput {
  direction: Direction;
  entryPrice: number;
  stopPrice: number;
  targetPrice: number;
  rangeHigh: number;
  rangeLow: number;
  targetHit: boolean;
  trailingStop: number | null;
  bar: { high: number; low: number; close: number; volume: number };
  entryTime: Date;
  now: Date;
  ema9: number;
}

export interface ExitResult {
  type: ExitType;
  price: number;
}

export function checkExit(input: ExitInput): ExitResult | null {
  const { direction, entryPrice, stopPrice, targetPrice, rangeHigh, rangeLow,
    targetHit, trailingStop, bar, entryTime, now, ema9 } = input;

  const minutesSinceEntry = (now.getTime() - entryTime.getTime()) / 60000;

  if (direction === "LONG") {
    if (targetHit && trailingStop && bar.low <= trailingStop) {
      return { type: "trail", price: trailingStop };
    }
    if (bar.low <= stopPrice) {
      return { type: "stop", price: stopPrice };
    }
    if (!targetHit && bar.close < rangeHigh && bar.close < entryPrice) {
      return { type: "failure", price: bar.close };
    }
    if (bar.high >= targetPrice) {
      return { type: "target", price: targetPrice };
    }
  } else {
    if (targetHit && trailingStop && bar.high >= trailingStop) {
      return { type: "trail", price: trailingStop };
    }
    if (bar.high >= stopPrice) {
      return { type: "stop", price: stopPrice };
    }
    if (!targetHit && bar.close > rangeLow && bar.close > entryPrice) {
      return { type: "failure", price: bar.close };
    }
    if (bar.low <= targetPrice) {
      return { type: "target", price: targetPrice };
    }
  }

  if (minutesSinceEntry >= DEFAULTS.timeExitMinutes) {
    return { type: "time", price: bar.close };
  }

  return null;
}

export function calcTrailingStop(direction: Direction, ema9: number): number {
  return ema9;
}
