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
9:30-9:45 AM: Build 9 ranges (3 tickers × 3 timeframes) → 9:35-11:30 AM: Monitor breakouts →
After signal: Track exits → 4:00 PM: Close, post summary, disconnect

### Path alias

`@/` maps to `src/`.
