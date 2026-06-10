# GO-LIVE PLAYBOOK

The exact procedure for moving from paper to real money. Do these in order. Do not skip gates.

## Step 1 — Run the verdict

```bash
npm run report:paper
```

- **KEEP COLLECTING** → not enough trades. Go back to vacation mode.
- **STOP** → the edge isn't showing up live. Do not spend a dollar. Diagnose first.
- **GO** → continue below.

## Step 2 — Pick your path (capital reality)

### Path A: Funded futures eval (recommended under $25k)
The engine's TQQQ/SOXL signals are Nasdaq/semis index signals — they map to **MNQ
(micro Nasdaq)** futures. Futures have **no PDT rule** and prop firms fund them.

1. Buy ONE eval (~$150, Apex/Topstep/MFF — wait for a discount, they run constantly).
   Pick a firm with **no eval consistency rule** if fast-passing (some cap any single
   day at 30-40% of total profit — read the rules before buying).
2. Mirror the engine's TQQQ entries manually on MNQ: same direction, same stop,
   EOD flatten. The Discord alert gives you everything at 6:35-7:30 AM your time.
3. Eval risk: 1-1.5% per trade (or the fast-pass variant: 3-4 contracts, reset on bust).
4. **Funded accounts use the SURVIVAL variant, not the engine variant.** A trailing
   drawdown punishes giving back open profits, so optimize for drawdown, not total R
   (our backtests: partial-taking halves max DD for ~25% less total R — the right
   trade under a trailing DD):
   - Take HALF off at +1R, move stop to breakeven on the rest, let it ride to EOD.
   - Risk per trade ≤ 0.5% AND ≤ 20% of your remaining drawdown headroom,
     whichever is smaller. Recompute headroom every morning.
   - Near the close, if the day is well green, flatten rather than donate it back —
     the trailing DD ratchets on your day's high-water mark.
5. Withdraw every month you're eligible. Expect the account to eventually die to the
   trailing drawdown — that's the model, not a failure. Withdrawals > fees = winning.
6. Scale: 1 account → verify a quarter → 3 → verify → more. Never all at once.

### Path B: Own capital, stocks (only if ≥ $26k)
**PDT rule**: a margin account under $25k gets 3 day trades per 5 business days.
The engine takes ~2-4 trades/DAY — it will trip PDT in one morning. Cash accounts
dodge PDT but can't short, and half our signals are shorts. So this path only works
at $26k+ equity. When you're there:

1. Open an Alpaca LIVE brokerage account, fund it, generate LIVE API keys.
2. In `.env.local`:
   ```
   ALPACA_API_KEY=<live key>
   ALPACA_API_SECRET=<live secret>
   ALPACA_TRADING_URL=https://api.alpaca.markets
   LIVE_CONFIRM=I_UNDERSTAND_REAL_MONEY
   ```
3. In `src/engine-stocks/config.ts`: set `RISK_PCT: 0.0025` (0.25%). Earn the right
   to raise it with 3 live months that match paper.
4. Restart: `scripts\start-stocks-engine.bat`. Startup will print
   `*** LIVE TRADING MODE ***` — if you don't see it, you're still on paper.

### Path C: Crypto live (works at any capital, weaker edge)
No PDT on crypto. Alpaca supports live crypto with the same API. The crypto ORB edge
was weaker (+4.7R/yr backtest, never walk-forward validated) — treat as experimental.

## Step 3 — Standing rules (all paths)

- Never touch strategy parameters mid-month.
- Kill switch: any -4R day = engine stops opening trades (built in).
- Monthly: `npm run report:paper` — live must stay inside the paper/backtest band.
- Quarterly: `npm run walkforward` — re-validate before changing ANY filter.
- Stop trading entirely if: 3 consecutive losing months, OR drawdown exceeds -25R,
  OR live avg R is below half of paper's after 50+ trades.
- The job stays until trading income > salary for 6 consecutive months.
