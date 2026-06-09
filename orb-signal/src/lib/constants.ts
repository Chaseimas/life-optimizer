import type { Ticker, TickerShort, Timeframe } from "./types";

export const TICKERS: Ticker[] = ["BTC/USD", "ETH/USD", "SOL/USD"];
export const TICKER_SHORT: Record<Ticker, TickerShort> = {
  "BTC/USD": "BTC",
  "ETH/USD": "ETH",
  "SOL/USD": "SOL",
};
export const TICKER_FULL: Record<TickerShort, Ticker> = {
  BTC: "BTC/USD",
  ETH: "ETH/USD",
  SOL: "SOL/USD",
};
export const TIMEFRAMES: Timeframe[] = [5, 10, 15];

export const ALPACA_REST_URL = "https://data.alpaca.markets";
export const ALPACA_WS_URL = "wss://stream.data.alpaca.markets/v1beta3/crypto/us";

export const DEFAULTS = {
  maxRangeAtrPct: 75,
  smaDowngradeThreshold: 0.5,
  smaSlopSkipThreshold: 0.2,
  candleQualityThreshold: 0.3,
  minVolumeRatio: 0.5,
  timeCutoffHour: 11,
  timeCutoffMinute: 30,
  selectionDelaySec: 120,
  timeExitMinutes: 120,
  maxTradesPerDay: 3,
  secondTradeScoreGap: 2,
} as const;

export const COLORS = {
  green: "#00c853",
  red: "#ff3d00",
  blue: "#4f8fea",
  bgPrimary: "#131722",
  bgSecondary: "#0f1319",
  bgCard: "#1c2230",
  border: "#2d3748",
} as const;
