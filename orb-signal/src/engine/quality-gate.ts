import { DEFAULTS } from "@/lib/constants";
import type { GradeOrSkip } from "@/lib/types";

export interface QualityInput {
  rangeWidth: number;
  atr14: number;
  volume: number;
  avgVolume: number;
  smaSlope: number;
}

export interface QualityResult {
  grade: GradeOrSkip;
  skipReason: string | null;
  rangeAtrPct: number;
  slopeDowngrade: boolean;
}

export function gradeRange(input: QualityInput): QualityResult {
  const { rangeWidth, atr14, volume, avgVolume, smaSlope } = input;
  const rangeAtrPct = (rangeWidth / atr14) * 100;
  const absSlope = Math.abs(smaSlope);

  if (absSlope < DEFAULTS.smaSlopSkipThreshold) {
    return { grade: "SKIP", skipReason: "SMA flat — stagnant market", rangeAtrPct, slopeDowngrade: false };
  }

  if (volume < avgVolume * DEFAULTS.minVolumeRatio) {
    return { grade: "SKIP", skipReason: "Low volume on opening range", rangeAtrPct, slopeDowngrade: false };
  }

  if (rangeAtrPct > DEFAULTS.maxRangeAtrPct) {
    return { grade: "SKIP", skipReason: `Range ${rangeAtrPct.toFixed(0)}% of ATR — too wide`, rangeAtrPct, slopeDowngrade: false };
  }

  // Breakout room check: range must use less than half the ATR so there is
  // enough runway beyond the range. This only applies to would-be A/B grades;
  // C grades (60-75%) inherently have less room but are still tradeable.
  if (rangeAtrPct < 60 && rangeAtrPct > 50) {
    return { grade: "SKIP", skipReason: "Not enough breakout room", rangeAtrPct, slopeDowngrade: false };
  }

  const slopeDowngrade = absSlope < DEFAULTS.smaDowngradeThreshold;

  let grade: GradeOrSkip;
  if (rangeAtrPct < 40) grade = "A";
  else if (rangeAtrPct < 60) grade = "B";
  else grade = "C";

  return { grade, skipReason: null, rangeAtrPct, slopeDowngrade };
}
