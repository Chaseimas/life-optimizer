# CLAUDE.md

## Commands

```bash
npm run dev          # Next.js dev server (localhost:3000)
npm run engine       # Signal engine background process
npm run build        # Production build
npm run test         # Vitest (run once)
npm run test:watch   # Vitest watch mode
```

## Architecture

Two-process system:

1. **Next.js app** (`npm run dev`) — serves dashboard UI and API routes
2. **Signal engine** (`npm run engine`) — connects to Alpaca crypto WebSocket, detects ORB breakouts, sends Discord alerts

Both share a SQLite database at `data/orb.db`.

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
