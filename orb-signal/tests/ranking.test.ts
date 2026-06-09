import { describe, it, expect } from "vitest";
import { calcCompositeScore, selectTrades, type RankingInput } from "@/engine/ranking";

function makeInput(overrides: Partial<RankingInput> = {}): RankingInput {
  return {
    grade: "A",
    gapAligned: true,
    smaSlope: 2.0,
    direction: "LONG",
    vwapDistance: 0.5,
    breakoutVolumeRatio: 1.8,
    candleQuality: 0.85,
    slopeDowngrade: false,
    ...overrides,
  };
}

describe("calcCompositeScore", () => {
  it("returns max score for ideal setup", () => {
    const score = calcCompositeScore(makeInput({
      grade: "A", gapAligned: true, smaSlope: 3.0,
      vwapDistance: 1.0, breakoutVolumeRatio: 3.0, candleQuality: 1.0,
    }));
    expect(score.total).toBeGreaterThanOrEqual(10);
  });

  it("returns lower score for grade C", () => {
    const a = calcCompositeScore(makeInput({ grade: "A" }));
    const c = calcCompositeScore(makeInput({ grade: "C" }));
    expect(a.total).toBeGreaterThan(c.total);
  });

  it("penalizes counter-gap", () => {
    const aligned = calcCompositeScore(makeInput({ gapAligned: true }));
    const counter = calcCompositeScore(makeInput({ gapAligned: false }));
    expect(aligned.total).toBeGreaterThan(counter.total);
  });

  it("applies slope downgrade", () => {
    const normal = calcCompositeScore(makeInput({ slopeDowngrade: false }));
    const downgraded = calcCompositeScore(makeInput({ slopeDowngrade: true }));
    expect(normal.total).toBeGreaterThan(downgraded.total);
  });
});

describe("selectTrades", () => {
  it("selects the top signal", () => {
    const signals = [
      { id: 1, ticker: "BTC", score: 9, grade: "A" as const },
      { id: 2, ticker: "ETH", score: 6, grade: "B" as const },
    ];
    const selected = selectTrades(signals);
    expect(selected).toHaveLength(1);
    expect(selected[0].id).toBe(1);
  });

  it("selects two when both are Grade A within 2 pts", () => {
    const signals = [
      { id: 1, ticker: "BTC", score: 9, grade: "A" as const },
      { id: 2, ticker: "ETH", score: 8, grade: "A" as const },
    ];
    const selected = selectTrades(signals);
    expect(selected).toHaveLength(2);
  });

  it("caps at 3 trades", () => {
    const signals = [
      { id: 1, ticker: "BTC", score: 9, grade: "A" as const },
      { id: 2, ticker: "ETH", score: 9, grade: "A" as const },
      { id: 3, ticker: "SOL", score: 9, grade: "A" as const },
    ];
    const selected = selectTrades(signals);
    expect(selected).toHaveLength(3);
  });

  it("never selects two trades on same ticker", () => {
    const signals = [
      { id: 1, ticker: "BTC", score: 9, grade: "A" as const },
      { id: 2, ticker: "BTC", score: 8.5, grade: "A" as const },
    ];
    const selected = selectTrades(signals);
    expect(selected).toHaveLength(1);
  });
});
