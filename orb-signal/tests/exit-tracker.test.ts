import { describe, it, expect } from "vitest";
import { checkExit, type ExitInput } from "@/engine/exit-tracker";

function makeLong(overrides: Partial<ExitInput> = {}): ExitInput {
  return {
    direction: "LONG",
    entryPrice: 64300,
    stopPrice: 63800,
    targetPrice: 64800,
    rangeHigh: 64200,
    rangeLow: 63800,
    targetHit: false,
    trailingStop: null,
    bar: { high: 64500, low: 64250, close: 64450, volume: 100 },
    entryTime: new Date("2026-06-09T09:47:00"),
    now: new Date("2026-06-09T10:30:00"),
    ema9: 64350,
    ...overrides,
  };
}

describe("checkExit", () => {
  it("returns null when no exit condition met", () => {
    expect(checkExit(makeLong())).toBeNull();
  });

  it("detects target hit for LONG", () => {
    const result = checkExit(makeLong({
      bar: { high: 64850, low: 64300, close: 64820, volume: 100 },
    }));
    expect(result).not.toBeNull();
    expect(result!.type).toBe("target");
    expect(result!.price).toBe(64800);
  });

  it("detects stop hit for LONG", () => {
    const result = checkExit(makeLong({
      bar: { high: 64000, low: 63750, close: 63780, volume: 100 },
    }));
    expect(result).not.toBeNull();
    expect(result!.type).toBe("stop");
  });

  it("detects failure exit (close back inside range) for LONG", () => {
    const result = checkExit(makeLong({
      bar: { high: 64250, low: 64050, close: 64100, volume: 100 },
    }));
    expect(result).not.toBeNull();
    expect(result!.type).toBe("failure");
  });

  it("detects trailing stop after target hit", () => {
    const result = checkExit(makeLong({
      targetHit: true,
      trailingStop: 64400,
      bar: { high: 64450, low: 64350, close: 64380, volume: 100 },
    }));
    expect(result).not.toBeNull();
    expect(result!.type).toBe("trail");
  });

  it("detects time exit after 2 hours", () => {
    const result = checkExit(makeLong({
      now: new Date("2026-06-09T11:50:00"),
    }));
    expect(result).not.toBeNull();
    expect(result!.type).toBe("time");
  });

  it("detects SHORT target", () => {
    const result = checkExit(makeLong({
      direction: "SHORT",
      entryPrice: 63700,
      stopPrice: 64200,
      targetPrice: 63200,
      bar: { high: 63300, low: 63150, close: 63180, volume: 100 },
    }));
    expect(result).not.toBeNull();
    expect(result!.type).toBe("target");
  });
});
