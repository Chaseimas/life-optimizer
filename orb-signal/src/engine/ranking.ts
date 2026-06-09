import { DEFAULTS } from "@/lib/constants";
import type { Grade, Direction, CompositeScore } from "@/lib/types";

export interface RankingInput {
  grade: Grade;
  gapAligned: boolean;
  smaSlope: number;
  direction: Direction;
  vwapDistance: number;
  breakoutVolumeRatio: number;
  candleQuality: number;
  slopeDowngrade: boolean;
}

export function calcCompositeScore(input: RankingInput): CompositeScore {
  const gradeWeight = input.grade === "A" ? 3 : input.grade === "B" ? 2 : 1;
  const gapAlignment = input.gapAligned ? 2 : -1;

  const absSlope = Math.abs(input.smaSlope);
  const smaStrength = Math.min(2, absSlope / 2.5 * 2);

  const vwapDistance = Math.min(2, input.vwapDistance * 2);
  const breakoutVolume = Math.min(2, (input.breakoutVolumeRatio - 1) * 2);
  const candleQuality = Math.min(1, input.candleQuality);

  let total = gradeWeight + gapAlignment + smaStrength + vwapDistance +
    Math.max(0, breakoutVolume) + candleQuality;

  if (input.slopeDowngrade) total -= 2;

  return { gradeWeight, gapAlignment, smaStrength, vwapDistance, breakoutVolume, candleQuality, total };
}

export function selectTrades(
  signals: { id: number; ticker: string; score: number; grade: Grade }[]
): typeof signals {
  if (signals.length === 0) return [];

  const sorted = [...signals].sort((a, b) => b.score - a.score);
  const selected = [sorted[0]];
  const topScore = sorted[0].score;
  const usedTickers = new Set([sorted[0].ticker]);

  for (let i = 1; i < sorted.length && selected.length < DEFAULTS.maxTradesPerDay; i++) {
    const candidate = sorted[i];
    if (usedTickers.has(candidate.ticker)) continue;
    if (candidate.grade !== "A") continue;
    if (topScore - candidate.score > DEFAULTS.secondTradeScoreGap) continue;
    selected.push(candidate);
    usedTickers.add(candidate.ticker);
  }

  return selected;
}
