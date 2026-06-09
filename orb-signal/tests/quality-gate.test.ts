import { describe, it, expect } from "vitest";
import { gradeRange, type QualityInput } from "@/engine/quality-gate";

function makeInput(overrides: Partial<QualityInput> = {}): QualityInput {
  return {
    rangeWidth: 400,
    atr14: 1500,
    volume: 1000,
    avgVolume: 800,
    smaSlope: 2.0,
    ...overrides,
  };
}

describe("gradeRange", () => {
  it("grades A when range < 40% of ATR", () => {
    const result = gradeRange(makeInput({ rangeWidth: 500, atr14: 1500 }));
    expect(result.grade).toBe("A");
    expect(result.skipReason).toBeNull();
  });

  it("grades B when range 40-60% of ATR", () => {
    const result = gradeRange(makeInput({ rangeWidth: 750, atr14: 1500 }));
    expect(result.grade).toBe("B");
  });

  it("grades C when range 60-75% of ATR", () => {
    const result = gradeRange(makeInput({ rangeWidth: 1000, atr14: 1500 }));
    expect(result.grade).toBe("C");
  });

  it("SKIPs when range > 75% of ATR", () => {
    const result = gradeRange(makeInput({ rangeWidth: 1200, atr14: 1500 }));
    expect(result.grade).toBe("SKIP");
    expect(result.skipReason).toContain("ATR");
  });

  it("SKIPs when not enough breakout room", () => {
    const result = gradeRange(makeInput({ rangeWidth: 800, atr14: 1500 }));
    expect(result.grade).toBe("SKIP");
    expect(result.skipReason).toContain("room");
  });

  it("SKIPs when volume too low", () => {
    const result = gradeRange(makeInput({ volume: 300, avgVolume: 800 }));
    expect(result.grade).toBe("SKIP");
    expect(result.skipReason).toContain("volume");
  });

  it("SKIPs when SMA slope is flat (stagnant)", () => {
    const result = gradeRange(makeInput({ smaSlope: 0.1 }));
    expect(result.grade).toBe("SKIP");
    expect(result.skipReason).toContain("stagnant");
  });

  it("downgrades by noting stagnant when slope is borderline", () => {
    const result = gradeRange(makeInput({ smaSlope: 0.4 }));
    expect(result.grade).not.toBe("SKIP");
    expect(result.slopeDowngrade).toBe(true);
  });
});
