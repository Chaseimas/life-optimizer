export type Ticker = "BTC/USD" | "ETH/USD" | "SOL/USD";
export type TickerShort = "BTC" | "ETH" | "SOL";
export type Timeframe = 5 | 10 | 15;
export type Direction = "LONG" | "SHORT";
export type Grade = "A" | "B" | "C";
export type GradeOrSkip = Grade | "SKIP";
export type Outcome = "WIN" | "LOSS" | "SCRATCH";
export type ExitType = "target" | "stop" | "trail" | "failure" | "time" | "eod";
export type GapDirection = "UP" | "DOWN" | "FLAT";
export type SessionPhase = "IDLE" | "PRE_SESSION" | "BUILDING_RANGES" | "MONITORING" | "TRACKING" | "CLOSED";

export interface Bar {
  timestamp: Date;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  symbol: string;
}

export interface DailyContext {
  ticker: TickerShort;
  priorDayHigh: number;
  priorDayLow: number;
  priorDayClose: number;
  premarketPrice: number;
  sma20: number;
  smaSlope: number;
  atr14: number;
  gapPct: number;
  gapDirection: GapDirection;
}

export interface OpeningRange {
  ticker: TickerShort;
  timeframe: Timeframe;
  rangeHigh: number;
  rangeLow: number;
  rangeWidth: number;
  openPrice: number;
  closePrice: number;
  volume: number;
  vwapAtClose: number;
  grade: GradeOrSkip;
  skipReason: string | null;
  rangeAtrPct: number;
}

export interface Signal {
  ticker: TickerShort;
  timeframe: Timeframe;
  direction: Direction;
  grade: Grade;
  entryPrice: number;
  stopPrice: number;
  targetPrice: number;
  risk: number;
  vwapAtEntry: number;
  breakoutVolumeRatio: number;
  breakoutCandleQuality: number;
  rankingScore: number;
  gapAligned: boolean;
  trendAligned: boolean;
  smaSlope: number;
  rangeAtrPct: number;
  gapPct: number;
  signalTime: Date;
}

export interface ActiveSignal extends Signal {
  outcome: Outcome | null;
  exitType: ExitType | null;
  exitPrice: number | null;
  exitTime: Date | null;
  rMultiple: number | null;
  targetHit: boolean;
  maxFavorable: number;
  maxAdverse: number;
}

export interface AlpacaBar {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
  n: number;
  vw: number;
}

export interface CompositeScore {
  gradeWeight: number;
  gapAlignment: number;
  smaStrength: number;
  vwapDistance: number;
  breakoutVolume: number;
  candleQuality: number;
  total: number;
}
