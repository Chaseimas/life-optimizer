# ORB Crypto Signal Dashboard — Design Spec

An automated Opening Range Breakout signal tool for cryptocurrency that scans multiple timeframes, detects the highest-quality breakout each day, and alerts via Discord.

## Overview

**What:** A background signal engine + web dashboard that runs the ORB strategy on crypto (BTC, ETH, SOL) using professional-grade filters. It scans all three timeframes (5, 10, 15-min) simultaneously and picks the single best trade each day. Sends Discord alerts so the user gets notified at work without watching screens.

**Who:** Built for personal use. User is away from screens during the session — fully autonomous.

**What it does NOT do:** Execute trades. It identifies signals and alerts the user.

**Why crypto:** Backtested across US stocks (SPY, QQQ, AAPL, TSLA, NVDA, AMD, IWM), futures (ES, NQ, YM, CL), and crypto (BTC, ETH, SOL) in growth, stagnant, and decline market phases. Crypto dominated every trending condition — 78% win rate in growth (10-min), 83% in decline (15-min). Stocks peaked at 67% in growth only. Futures never exceeded 44%.

## The ORB Strategy

### Phase 1: Pre-Session Context (9:00–9:30 AM ET)

The engine uses the US market open (9:30 AM ET) as the crypto session anchor — this is when institutional volume spikes and clean breakout structures form.

Before the opening range forms, the engine gathers:

- **Prior day levels:** Yesterday's high, low, and close (using 00:00–23:59 UTC daily candle). Key support/resistance zones.
- **Pre-market price:** Price just before 9:30 AM ET. Used to calculate the gap.
- **Gap:** Difference between pre-session price and prior daily close. Long breakouts on gap-up days hit targets ~74% vs ~48% on gap-down days.
- **20-day SMA:** Higher-timeframe trend filter. Only take longs above it, shorts below it.
- **SMA slope:** Rate of change of the 20-SMA over the last 5 days. If the SMA is flat (slope near zero), the market is stagnant — reduce signal confidence or skip entirely. Steep slopes = trending = where ORB excels.
- **14-day ATR:** Judges whether the opening range is normal-sized for this asset.

### Phase 2: Multi-Timeframe Range Construction (9:30 AM ET →)

This is the key differentiator. Instead of committing to one timeframe, the engine builds **three opening ranges simultaneously:**

| Timeframe | Range locks at | Best in |
|-----------|---------------|---------|
| 5-min | 9:35 AM | Fast-moving trending markets |
| 10-min | 9:40 AM | Growth phases (78% WR in backtest) |
| 15-min | 9:45 AM | Decline phases (83% WR in backtest) |

For each ticker × timeframe combination, record:
- `range_high`, `range_low`, `range_width`
- Opening range volume, VWAP at range close, open price

That's 9 ranges total (3 tickers × 3 timeframes), all monitored in parallel.

### Phase 3: Signal Quality Gate

Each of the 9 ticker/timeframe combos is independently filtered. If any check fails, that combo is marked "no trade" with the reason logged.

**Filters (all must pass):**

1. **Trend alignment (20-day SMA):** Longs require price above 20-SMA. Shorts require below. The single most important filter — counter-trend breakouts fail far more often.

2. **SMA slope filter:** If the 20-SMA's 5-day rate of change is within ±0.5%, the market is stagnant. Downgrade the signal by 2 points in ranking (still tradeable but less likely to be selected). If within ±0.2%, skip entirely — no edge in choppy conditions.

3. **Range vs ATR:** Skip if range > 75% of ATR (daily move already spent). Grade:
   - **A:** Range < 40% of ATR (plenty of room)
   - **B:** Range 40–60% of ATR (decent)
   - **C:** Range 60–75% of ATR (borderline)

4. **Volume check:** Skip if opening range volume is below 50% of the ticker's trailing 10-day average first-candle volume.

5. **Breakout room:** Remaining ATR (ATR minus range width) must exceed the range width. If there's less room to run than you're risking, skip.

### Phase 4: Breakout Detection (range close → 11:30 AM ET)

After each range locks and passes quality:

- Monitor **1-minute candle closes** against range boundaries
- **Long breakout (ALL must be true):**
  - 1-min candle closes above `range_high`
  - Close is in the **top 30%** of the candle's range (strong close)
  - Price is **above VWAP**
  - Breakout candle volume above average
- **Short breakout (ALL must be true):**
  - 1-min candle closes below `range_low`
  - Close is in the **bottom 30%** of the candle's range
  - Price is **below VWAP**
  - Breakout candle volume above average

**Smart trade selection — quality over quantity.**

The default is ONE trade per day. But if multiple tickers produce genuinely strong setups, take them both rather than leaving money on the table. The rules:

1. **Always take the #1 ranked signal.** This is the primary trade.
2. **Take a second trade ONLY IF** the #2 signal is also Grade A, its composite score is within 2 points of #1, and it's on a different ticker (never two trades on the same asset).
3. **Up to 3 trades per day.** If all three tickers produce Grade A setups with scores within 2 points of each other, take all three. This is rare but when it happens, the trend is strong across the board.
4. **Never force a trade.** If no signal passes all filters, post "No trade today" and move on. Sitting out is always an option.

Example: BTC and ETH both fire Grade A breakouts within 2 minutes, both scoring 8+ out of 10. Take both. But if BTC scores 9 and SOL scores 5, just take BTC.

**Composite ranking:**

1. **Grade weight** — A = 3 pts, B = 2 pts, C = 1 pt
2. **Gap alignment** — signal matches gap direction = +2 pts; against = -1 pt
3. **SMA slope strength** — steeper trend in signal direction = +0 to 2 pts
4. **VWAP distance** — further from VWAP in signal direction = stronger, +0 to 2 pts
5. **Breakout volume** — higher relative volume = more conviction, +0 to 2 pts
6. **Candle quality** — close position within range, closer to extreme = +0 to 1 pt

Max composite score: ~12 pts. The engine waits 2 minutes after the first valid breakout to see if others fire, then commits to the best (and optionally second-best).

**Time cutoff: 11:30 AM ET.** No new signals after this.

### Phase 5: Exit Levels & Outcome Tracking

**Stop loss:** Opposite end of the opening range. Long → stop at range low. Short → stop at range high.

**Target (measured move):** Range width projected from entry. Long: `entry + range_width`. Short: `entry - range_width`. A 1:1 R trade.

**Trailing stop (after target):** Once target is hit, stop moves to breakeven. Then trails below 9-EMA (5-min chart) for longs, above for shorts.

**Failure exit:** If a 1-min candle closes back inside the opening range after entry, get out immediately.

**Time exit:** If neither target nor stop hit within 2 hours, log as scratch.

**End of day (4:00 PM ET):** Close any open signal.

**Outcomes:** WIN (hit target or trailed out above entry), LOSS (hit stop or failure exit), SCRATCH (time exit near entry).

### Phase 6: Gap Context

Included in every alert — materially affects expected win rate:

- Gap-up + Long → highest probability (~74%)
- Gap-down + Short → second-best (continuation)
- Counter-gap setups → lower probability

## Architecture

### 1. Signal Engine (Node.js background service)

- **Pre-session (9:00 AM ET):** Fetches prior day data, calculates SMA, ATR, SMA slope, gap for BTC, ETH, SOL via Alpaca REST API.
- **Session start (9:25 AM):** Connects to Alpaca crypto WebSocket. Posts session context to Discord.
- **Range phase (9:30–9:45 AM):** Builds all 9 ranges (3 tickers × 3 timeframes) simultaneously. Posts range quality as each locks.
- **Monitoring (9:35–11:30 AM):** Watches 1-min candle closes against all active ranges. Ranks signals by composite score. Fires alert for the best.
- **Tracking (signal → 4:00 PM):** Monitors target, stop, failure, trailing stop. Posts updates.
- **Close (4:00 PM):** Final exit, daily summary, disconnect.

### 2. Web Dashboard (Next.js)

- **Live View** — all 9 ranges displayed as visual bars, current price overlaid, status per combo
- **History** — past signals with outcomes, win rates, performance by grade/ticker/timeframe
- **Settings** — watchlist, filter toggles, Discord webhook

### 3. SQLite Database

Shared between services. Single user.

## Discord Alerts

Webhook-based (no bot needed).

**Session start (9:25 AM):**
```
ORB Session Starting
Watching: BTC, ETH, SOL
Timeframes: 5 / 10 / 15 min (auto-pick best)
BTC: above 20-SMA | gap +1.2% UP | slope: +2.1% (trending)
ETH: above 20-SMA | gap +0.8% UP | slope: +1.8% (trending)
SOL: below 20-SMA | gap -0.5% DN | slope: -1.4% (shorts only)
```

**Range established:**
```
BTC 10-min Range Set  [A]
High: $64,280 | Low: $63,850 | Width: $430
VWAP: $64,100 | ATR: $1,450 (range = 30%)
Volume: 142% of avg
Watching for breakout...
```

**Primary trade:**
```
ORB LONG — BTC 10-min  [A]  #1 SETUP
Entry:   $64,300
Stop:    $63,850 (range low)
Target:  $64,730 (measured move, 1R)
Risk:    $450
---
Above VWAP ($64,100)
Trend: above 20-SMA, slope +2.1%
Gap: +1.2% (with gap)
Breakout vol: 185% of avg
Score: 9.2 / 12 — Ranked #1
---
Timeframe: 10-min (scored highest across 5/10/15)
Trade 1 of 1 today.
```

**Second trade (only when both are strong):**
```
ORB LONG — ETH 10-min  [A]  #2 SETUP (also strong)
Entry:   $2,485
Stop:    $2,462 (range low)
Target:  $2,508 (measured move, 1R)
Risk:    $23
---
Above VWAP ($2,478)
Trend: above 20-SMA, slope +1.8%
Gap: +0.8% (with gap)
Breakout vol: 162% of avg
Score: 8.5 / 12 — within 2 pts of #1
---
Both BTC and ETH showing Grade A setups. Taking both.
Trade 2 of 2 today.
```

**Target hit:**
```
BTC LONG — Target hit at $64,730 (+$430, 1R)
Stop moved to breakeven ($64,300).
Trail below 9-EMA for the runner.
```

**Trade closed:**
```
BTC LONG — Done.
Exit: $65,100 (trailed out)
Result: +$800 (1.8R) WIN
```

**No trade today (11:30 AM):**
```
No trade today.
BTC: range too wide (82% of ATR)
ETH: below VWAP at breakout
SOL: SMA flat, skipped (stagnant)
No setup worth the risk. Sitting out.
```

**Daily summary (4:00 PM):**
```
ORB Daily Summary — Jun 9
Trade 1: BTC LONG 10-min [A] -> WIN +$800 (1.8R)
Trade 2: ETH LONG 10-min [A] -> WIN +$28 (1.2R)
---
Skipped: SOL (SMA flat — stagnant)
---
Running: 68% win rate (17W-8L)
Grade A signals: 75% win rate
Best timeframe: 10-min (72% WR)
```

## Web Dashboard Detail

### Live View (home page)

**Top bar:** Market status, tickers watched, today's trade status.

**Range grid:** 3 tickers × 3 timeframes = 9 cards. Each shows:
- Range as a visual bar (low—high) with current price marker and VWAP line
- Status: "Building..." → "Watching..." → "LONG [A]" / "Skipped" / "No breakout"
- Grade badge, filter results, volume status
- Highlighted border on the selected (best) signal

**Active trade panel (when signal fires):**
- Entry, stop, target, current P/L, trailing stop level
- Time since entry, R multiple updating live

### History Page

- **Summary stats:** total signals, win rate, avg R, best streak, profit factor
- **Breakdowns:** by grade (A/B/C), by ticker (BTC/ETH/SOL), by timeframe (5/10/15), by direction (LONG/SHORT), by market phase
- **Table:** date, ticker, timeframe, direction, grade, entry, exit, outcome, R, exit type

### Settings Page

**Tickers:** BTC, ETH, SOL (add/remove)

**Timeframes:** Toggle which to scan (5/10/15 min, all on by default)

**Filters:**
- Trend filter (20-SMA): ON/OFF
- SMA slope stagnant threshold: default ±0.5% (downgrade), ±0.2% (skip)
- VWAP alignment: ON/OFF
- Candle close quality (30%): ON/OFF
- Volume on breakout: ON/OFF
- Max range vs ATR: default 75%
- Time cutoff: default 11:30 AM ET

**Exits:**
- Target: measured move / 1R
- Trailing stop: 9-EMA or VWAP
- Failure exit: ON/OFF
- Time exit (2 hours): ON/OFF

**Alerts:**
- Discord webhook URL + test button
- Alert skipped signals: ON/OFF
- Alert updates: ON/OFF

## Data Model

### signals

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| ticker | TEXT | "BTC", "ETH", "SOL" |
| date | TEXT | Trading date (YYYY-MM-DD) |
| timeframe | INTEGER | 5, 10, or 15 (minutes) |
| direction | TEXT | "LONG" or "SHORT" |
| grade | TEXT | "A", "B", "C" |
| range_high | REAL | Opening range high |
| range_low | REAL | Opening range low |
| range_width | REAL | High minus low |
| entry_price | REAL | Breakout candle close |
| stop_price | REAL | Stop loss |
| target_price | REAL | Measured move target |
| risk | REAL | Entry to stop distance |
| signal_time | TEXT | ISO timestamp |
| vwap_at_entry | REAL | VWAP at breakout |
| breakout_volume_ratio | REAL | Breakout vol / avg vol |
| breakout_candle_quality | REAL | Close position in range (0–1) |
| outcome | TEXT | "WIN", "LOSS", "SCRATCH", NULL |
| exit_type | TEXT | "target", "stop", "trail", "failure", "time", "eod" |
| exit_price | REAL | Price at exit |
| exit_time | TEXT | When exited |
| r_multiple | REAL | Actual R achieved |
| target_hit | INTEGER | 1 if target reached |
| ranking_score | REAL | Composite score |
| was_selected | INTEGER | 1 if this was today's trade |
| max_favorable | REAL | Best price in signal direction |
| max_adverse | REAL | Worst price against signal |
| skipped | INTEGER | 1 if filtered out |
| skip_reason | TEXT | Why skipped |
| range_atr_pct | REAL | Range as % of ATR |
| gap_pct | REAL | Gap as % of prior close |
| gap_aligned | INTEGER | 1 if direction matches gap |
| trend_aligned | INTEGER | 1 if aligns with SMA |
| sma_slope | REAL | 20-SMA 5-day slope % |

### opening_ranges

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| ticker | TEXT | "BTC", "ETH", "SOL" |
| date | TEXT | Trading date |
| timeframe | INTEGER | 5, 10, or 15 |
| range_high | REAL | High of range candle |
| range_low | REAL | Low of range candle |
| range_width | REAL | High minus low |
| open_price | REAL | Session open price |
| close_price | REAL | Range candle close |
| volume | REAL | Range candle volume |
| vwap_at_close | REAL | VWAP when range locked |
| atr_14 | REAL | 14-day ATR |
| sma_20 | REAL | 20-day SMA |
| sma_slope | REAL | SMA rate of change |
| prior_day_high | REAL | Yesterday's high |
| prior_day_low | REAL | Yesterday's low |
| prior_day_close | REAL | Yesterday's close |
| premarket_price | REAL | Price just before session |
| gap_pct | REAL | Gap as % |
| gap_direction | TEXT | "UP", "DOWN", "FLAT" |
| quality_grade | TEXT | "A", "B", "C", "SKIP" |
| skip_reason | TEXT | Why skipped |

### settings

| Column | Type | Description |
|--------|------|-------------|
| key | TEXT PK | Setting name |
| value | TEXT | JSON-encoded value |

## Stack

- **Signal Engine:** Node.js, TypeScript, Alpaca crypto WebSocket + REST, better-sqlite3, node-cron
- **Web Dashboard:** Next.js (App Router), TypeScript, Tailwind CSS
- **Database:** SQLite via better-sqlite3
- **Alerts:** Discord webhook (HTTP POST)
- **Theme:** Dark (#131722 bg, #00c853 green, #ff3d00 red, #4f8fea blue)

## Deployment

- **Signal Engine:** Railway or PM2 on VPS (always-on)
- **Web Dashboard:** Vercel
- **Database:** SQLite on engine host

Simplest: run both on the same machine sharing the SQLite file.

## Scope

**v1:**
- Signal engine with Alpaca crypto WebSocket
- Multi-timeframe range construction (5/10/15 min simultaneous)
- Full quality gate with SMA slope stagnant detection
- Composite ranking across tickers AND timeframes
- One-trade-per-day discipline
- Exit system (target, stop, trailing, failure, time)
- Discord alerts
- Web dashboard (live view, history, settings)
- SQLite storage

**Later:**
- Trade execution
- Additional crypto pairs
- US stock support (secondary)
- Backtesting module
- Mobile push notifications
