import { describe, it, expect } from "vitest";
import { checkBreakout, type BreakoutInput } from "@/engine/breakout-detector";

function makeInput(overrides: Partial<BreakoutInput> = {}): BreakoutInput {
  return {
    bar: { open: 64100, high: 64350, low: 64050, close: 64300, volume: 500 },
    rangeHigh: 64200,
    rangeLow: 63800,
    vwap: 64100,
    sma20: 63000,
    avgBarVolume: 300,
    ...overrides,
  };
}

describe("checkBreakout", () => {
  it("detects LONG breakout when all conditions met", () => {
    const result = checkBreakout(makeInput());
    expect(result).not.toBeNull();
    expect(result!.direction).toBe("LONG");
  });

  it("rejects LONG when close below range high", () => {
    const result = checkBreakout(makeInput({
      bar: { open: 64000, high: 64100, low: 63900, close: 64050, volume: 500 },
    }));
    expect(result).toBeNull();
  });

  it("rejects LONG when close below VWAP", () => {
    const result = checkBreakout(makeInput({ vwap: 65000 }));
    expect(result).toBeNull();
  });

  it("rejects LONG when candle quality is weak (close in bottom of range)", () => {
    const result = checkBreakout(makeInput({
      bar: { open: 64250, high: 64300, low: 64050, close: 64080, volume: 500 },
    }));
    expect(result).toBeNull();
  });

  it("rejects LONG when below SMA (counter-trend)", () => {
    const result = checkBreakout(makeInput({ sma20: 70000 }));
    expect(result).toBeNull();
  });

  it("detects SHORT breakout", () => {
    const result = checkBreakout(makeInput({
      bar: { open: 63850, high: 63870, low: 63700, close: 63720, volume: 500 },
      vwap: 63900,
      sma20: 65000,
    }));
    expect(result).not.toBeNull();
    expect(result!.direction).toBe("SHORT");
  });

  it("returns candle quality and volume ratio in result", () => {
    const result = checkBreakout(makeInput());
    expect(result!.candleQuality).toBeGreaterThan(0.7);
    expect(result!.volumeRatio).toBeGreaterThan(1);
  });
});
