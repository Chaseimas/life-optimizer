/**
 * Stock ORB engine config — Zarattini-style 5-min ORB, 3R target, hold to EOD.
 *
 * Universe/filters are set from the walk-forward validation results
 * (src/backtest/run-walkforward.ts). Do not add filters that haven't
 * survived an out-of-sample test.
 */

export const STOCKS_CONFIG = {
  // Universe — selected by walk-forward data-integrity + sizing tests (2024-2026):
  //  - Dropped UPRO/FAS/TNA/ARM/COIN: 0-24% clean IEX days (sparse minute data)
  //  - Dropped SPY/QQQ: stops too tight (0.2-0.3% of price) — would trade at ~15% of
  //    intended risk under the notional cap and waste concurrent-position slots.
  //    TQQQ/SOXL carry the index exposure at full size instead.
  TICKERS: ["TQQQ", "SOXL", "TSLA", "NVDA", "AMD", "AAPL", "PLTR", "MARA", "SMCI", "MSTR"],

  // Strategy (fixed, from published research — not tuned knobs)
  ORB_MINUTES: 5,
  TARGET_R: 3,
  MIN_BODY_FRAC: 0.1,        // first 5-min candle body must be >= 10% of range
  ENTRY_CUTOFF_MIN: 10 * 60 + 30,  // no entries after 10:30 ET
  FLATTEN_MIN: 15 * 60 + 55,       // close everything at 3:55 PM ET

  // Optional filters — only enable what survives walk-forward (run-walkforward.ts)
  MWF_ONLY: false,           // FAILED validation: train year's best days were Tue+Fri
  DIR_FILTER: null as null | string[],  // direction×ticker filters showed only partial
                                        // persistence (7/10) — not baked in; re-derive quarterly

  // Risk
  RISK_PCT: 0.01,            // 1% of paper equity per trade (drop to 0.25-0.5% for live)
  MAX_NOTIONAL_PCT: 0.8,     // per-position notional cap (4 concurrent × 0.8 = 3.2x < 4x day BP)
  MAX_CONCURRENT: 4,         // max simultaneous positions
  DAILY_LOSS_LIMIT_R: 4,     // stop opening new trades after -4R day (safety brake)

  // Engine mechanics
  POLL_SECONDS: 15,
} as const;

// Trading endpoint. Defaults to PAPER. To go live (real money) you must set BOTH:
//   ALPACA_TRADING_URL=https://api.alpaca.markets
//   LIVE_CONFIRM=I_UNDERSTAND_REAL_MONEY
// (and use live API keys, not PK paper keys). See GOLIVE.md for the full checklist.
const requestedUrl = process.env.ALPACA_TRADING_URL ?? "https://paper-api.alpaca.markets";
if (requestedUrl.includes("api.alpaca.markets") && !requestedUrl.includes("paper")) {
  if (process.env.LIVE_CONFIRM !== "I_UNDERSTAND_REAL_MONEY") {
    throw new Error(
      "[config] ALPACA_TRADING_URL points at LIVE trading but LIVE_CONFIRM is not set. " +
      "Set LIVE_CONFIRM=I_UNDERSTAND_REAL_MONEY only after completing the GOLIVE.md checklist."
    );
  }
  console.log("[config] *** LIVE TRADING MODE — REAL MONEY ***");
}
export const TRADING_URL = requestedUrl;
export const IS_PAPER = requestedUrl.includes("paper");
