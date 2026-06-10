# CLAUDE.md

## Commands

```bash
npm run dev            # Next.js dev server (localhost:3000)
npm run engine         # Crypto signal engine (alerts only, no orders)
npm run engine:stocks  # Stock ORB engine — places REAL paper orders on Alpaca
npm run walkforward    # Out-of-sample validation (train yr1 → test yr2, costs on)
npm run report:paper   # Go/no-go readiness report: paper results vs backtest gates
npm run build          # Production build
npm run test           # Vitest (run once)
npm run test:watch     # Vitest watch mode
```

Going live (real money) is gated behind `GOLIVE.md` — env-var latch
(`ALPACA_TRADING_URL` + `LIVE_CONFIRM`), capital paths, PDT constraints, kill criteria.

## Architecture

Three-process system:

1. **Next.js app** (`npm run dev`) — serves dashboard UI and API routes
2. **Crypto signal engine** (`npm run engine`) — Alpaca crypto WebSocket, ORB breakout Discord alerts (signal-only)
3. **Stock paper-trading engine** (`npm run engine:stocks`) — Zarattini-style 5-min ORB on 10 stocks/ETFs; submits real bracket orders to the Alpaca **paper** account, tracks fills/slippage, Discord alerts, EOD flatten at 3:55 PM ET

All share the SQLite database at `data/orb.db` (`signals` table).

### Stock engine strategy (walk-forward validated, src/backtest/run-walkforward.ts)

- 5-min opening range (timestamp-verified vs sparse IEX data), trade only in the
  direction of the first 5-min candle, enter on first 1-min close beyond the range
  before 10:30 ET, stop = far side of range, target = 3R, otherwise hold to 3:55 PM.
  No breakeven, no trailing.
- Out-of-sample year B (costs on): +140R all-combos, PF 1.12; winners-filter procedure
  improved avg R 0.066→0.100 and PF to 1.18 (7/10 top combos persisted).
- MWF day-of-week filter FAILED validation — do not enable without re-validating.
- Universe excludes UPRO/FAS/TNA/ARM/COIN (0-24% clean IEX days) and SPY/QQQ
  (stops too tight to size at 1% risk — TQQQ/SOXL carry index exposure instead).
- Re-run `npm run walkforward` quarterly before changing any filter.

### Engine lifecycle (daily)

9:00 AM ET: Fetch daily bars, calc SMA/ATR/gap → 9:25 AM: Connect WebSocket, post session start →
9:30-9:40 AM: Build 4 ranges (2 tickers × 2 timeframes) → 9:35-11:30 AM: Monitor breakouts →
After signal: Track exits (breakeven stop at 0.15R, trail after target) → 4:00 PM: Close, post summary, disconnect

### Optimized config (backtest: +6.64R, 6.37x PF, -0.68R DD over 4 months)

- Tickers: ETH/USD, SOL/USD (BTC dropped — 0% ORB win rate)
- Timeframes: 5, 10 min (15m dropped — momentum fades)
- Score filter: composite ≥ 7 (6-7 range is dead zone)
- Breakeven stop: 0.15R (move stop to entry early)
- Selection delay: 60 sec (take first qualifying signal)

### Path alias

`@/` maps to `src/`.
