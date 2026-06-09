import { describe, it, expect } from "vitest";
import { calcSMA, calcATR, calcVWAP, calcEMA, calcSMASlope } from "@/lib/indicators";

describe("calcSMA", () => {
  it("calculates simple moving average", () => {
    const closes = [10, 12, 11, 13, 14];
    expect(calcSMA(closes, 5)).toBeCloseTo(12);
  });

  it("uses last N values when array is longer", () => {
    const closes = [5, 10, 12, 11, 13, 14];
    expect(calcSMA(closes, 5)).toBeCloseTo(12);
  });

  it("returns NaN when not enough data", () => {
    expect(calcSMA([10, 12], 5)).toBeNaN();
  });
});

describe("calcATR", () => {
  it("calculates average true range", () => {
    const bars = [
      { high: 102, low: 98, close: 100 },
      { high: 104, low: 99, close: 103 },
      { high: 105, low: 101, close: 102 },
      { high: 103, low: 97, close: 98 },
    ];
    const atr = calcATR(bars, 3);
    expect(atr).toBeGreaterThan(0);
    expect(atr).toBeLessThan(10);
  });
});

describe("calcVWAP", () => {
  it("calculates volume-weighted average price", () => {
    const bars = [
      { high: 102, low: 98, close: 100, volume: 1000 },
      { high: 104, low: 100, close: 103, volume: 2000 },
    ];
    const vwap = calcVWAP(bars);
    expect(vwap).toBeCloseTo(101.56, 1);
  });

  it("returns 0 for empty bars", () => {
    expect(calcVWAP([])).toBe(0);
  });
});

describe("calcEMA", () => {
  it("calculates exponential moving average", () => {
    const closes = [10, 11, 12, 13, 14, 15, 16, 17, 18];
    const ema = calcEMA(closes, 9);
    expect(ema).toBeGreaterThan(13);
    expect(ema).toBeLessThan(18);
  });
});

describe("calcSMASlope", () => {
  it("returns positive slope for uptrend", () => {
    const smaValues = [100, 101, 102, 103, 104];
    expect(calcSMASlope(smaValues)).toBeGreaterThan(0);
  });

  it("returns negative slope for downtrend", () => {
    const smaValues = [104, 103, 102, 101, 100];
    expect(calcSMASlope(smaValues)).toBeLessThan(0);
  });

  it("returns near-zero for flat", () => {
    const smaValues = [100, 100.1, 99.9, 100, 100.1];
    expect(Math.abs(calcSMASlope(smaValues))).toBeLessThan(0.5);
  });
});
