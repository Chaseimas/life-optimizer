# ORB Signal Dashboard — Design Spec

An automated Opening Range Breakout signal tool that monitors US stocks at market open, detects breakouts, and alerts via Discord.

## Overview

**What:** A background signal engine + web dashboard that implements the ORB (Opening Range Breakout) day trading strategy. It connects to Alpaca's real-time data at market open, builds the opening range from the first candle, monitors for breakouts, sends Discord alerts, and tracks outcomes over time.

**Who:** Built for personal use. User is away from screens at market open — the tool must be fully autonomous during market hours.

**What it does NOT do:** Execute trades. It identifies signals and alerts the user, who decides whether to act.

## The ORB Strategy

1. **Market opens** at 9:30 AM ET
2. **Opening range forms** during the first candle (configurable: 5, 15, or 30 minutes; default 5 min)
3. The candle's **high** and **low** define the range
4. **Long signal:** price closes a 1-minute confirmation candle above the range high
5. **Short signal:** price closes a 1-minute confirmation candle below the range low
6. **Stop loss:** opposite end of the range
7. **Target:** configurable risk/reward ratio (1:1, 1.5:1, or 2:1)

## Architecture

Two services:

### 1. Signal Engine (Node.js background service)

The always-on process that does the real work:

- **Pre-market (9:25 AM ET):** Wakes up, connects to Alpaca WebSocket for all configured tickers. Posts "Session starting" to Discord.
- **Opening range phase (9:30 → candle close):** Streams real-time bars, tracks high/low of the first candle. When the candle closes, locks in the opening range. Posts range to Discord.
- **Breakout monitoring (candle close → 4:00 PM):** Watches 1-minute candle closes against the range boundaries. On breakout, creates a signal record and fires a Discord alert.
- **End of day (4:00 PM):** Evaluates each signal — did price hit the target or stop first? Updates outcomes. Posts daily summary to Discord.
- **Post-market:** Disconnects WebSocket, sleeps until next trading day.

### 2. Web Dashboard (Next.js)

A lightweight web app for visibility and configuration:

- **Live View** — today's opening ranges and breakout status per ticker
- **History** — past signals with outcomes, win rates, performance stats
- **Settings** — manage watchlist, candle size, R/R target, Discord webhook URL

### 3. SQLite Database

Shared between both services. Single user, moderate data volume — SQLite is the right fit.

## Signal Engine Detail

### Alpaca WebSocket Connection

- Uses Alpaca's free-tier real-time data (IEX feed for free accounts, SIP for paid)
- Subscribes to 1-minute bars for all configured tickers
- Reconnects automatically on disconnect
- Only active during market hours (9:25 AM – 4:05 PM ET, weekdays, excluding market holidays)

### Opening Range Construction

For each ticker, during the first N minutes after 9:30 AM:

- Track the highest high and lowest low from incoming bars
- When the configured candle period ends (e.g., 9:35 AM for 5-min), freeze the range
- Store: `ticker`, `date`, `range_high`, `range_low`, `range_width`, `candle_size`, `open_price`

### Signal Quality Filter

Not every opening range produces a good trade. Before alerting, the engine checks:

- **Max risk per share:** Skip if range width exceeds a configurable cap (e.g., $2.00). A $3 wide range on SPY means risking $3/share to make $3 at 1:1 — not worth it for most setups.
- **Min range width:** Skip if range is too narrow (e.g., < $0.15). Extremely tight ranges whipsaw and produce false breakouts.
- **Max range as % of price:** Skip if range width is more than a configurable percentage of the stock price (e.g., 0.5%). Normalizes risk across different-priced tickers — $1 risk on a $50 stock is very different from $1 on a $500 stock.
- **Volume check:** Skip if the opening range candle's volume is abnormally low (below 50% of the ticker's average first-candle volume). Low volume ranges are unreliable.

When a signal is skipped, the engine still logs it to the database (with a `skipped` flag and the reason) and posts a muted Discord message so you can review whether the filters are too aggressive:

```
⏭️ SPY — LONG breakout skipped
Reason: Range too wide ($2.85 risk, max $2.00)
```

All filter thresholds are configurable in Settings.

### Breakout Detection

After the range is locked and passes the quality filter:

- Monitor each 1-minute candle close
- **Long breakout:** 1-min candle closes above `range_high`
- **Short breakout:** 1-min candle closes below `range_low`
- Only the FIRST breakout per direction per ticker per day is signaled (avoid duplicate alerts)
- A ticker can produce both a long and short signal in the same day (if price whipsaws)

### Signal Record

Each signal stores:
- `ticker`, `date`, `direction` (LONG/SHORT)
- `entry_price` (the breakout candle's close)
- `stop_price` (opposite end of range)
- `target_price` (entry ± range_width × R/R multiplier)
- `risk_per_share` (range width)
- `signal_time`
- `outcome` (WIN/LOSS/OPEN — updated at end of day)
- `outcome_time` (when target or stop was hit)
- `max_favorable` (best price in the signal's direction — for analysis)
- `max_adverse` (worst price against the signal — for analysis)

### Outcome Evaluation

Runs continuously after each signal fires, and also at end of day:

- Tracks whether price hits target or stop first using incoming bar data
- **WIN:** price reached the target price
- **LOSS:** price reached the stop price
- **OPEN:** neither hit by 4:00 PM (marked as a scratch/flat)

### Discord Alerts

Uses a simple webhook (no bot needed). Three message types:

**Session start (9:25 AM):**
```
📊 ORB Session Starting
Watching: SPY, QQQ, AAPL
Candle: 5 min | R/R: 1.5:1
```

**Range established (after first candle closes):**
```
📐 SPY Opening Range Set
High: $543.10 | Low: $542.30
Width: $0.80
Watching for breakout...
```

**Breakout signal:**
```
🟢 ORB LONG — SPY
━━━━━━━━━━━━━━━━━━
Entry:   $543.12
Stop:    $542.30 (range low)
Target:  $544.32 (1.5:1 R/R)
Risk:    $0.82/share
Range:   $542.30 — $543.10
Time:    9:37 AM ET
```

(🔴 for SHORT signals)

**Daily summary (4:00 PM):**
```
📋 ORB Daily Summary — Jun 8
━━━━━━━━━━━━━━━━━━━━━━━━━━━
SPY:  🟢 LONG → ✅ WIN (+$1.22)
QQQ:  🔴 SHORT → ❌ LOSS (-$0.65)
AAPL: No breakout
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Today: 1W / 1L | Running: 58% win rate
```

## Web Dashboard Detail

### Live View (home page)

Per-ticker cards showing:
- **Opening range** as a visual bar (low—high) with current price marker
- **Status badge:** "Building range…" → "Watching…" → "LONG ✅" / "SHORT 🔴" / "No breakout"
- **Signal details** (if triggered): entry, stop, target, current P/L
- **Time info:** time since open, time since signal

Top bar shows: market status (pre-market / open / closed), number of tickers watched, today's signal count.

### History Page

- **Summary stats at top:** total signals, win rate, average R achieved, best streak, worst streak, profit factor
- **Filterable table:** date, ticker, direction, entry, stop, target, outcome, R multiple, duration
- **Filters:** ticker dropdown, direction (long/short/both), outcome (win/loss/all), date range
- **Per-ticker breakdown:** which tickers have the best ORB win rate

### Settings Page

- **Watchlist:** add/remove tickers (text input with validation against Alpaca symbols)
- **Candle size:** 5 / 15 / 30 minutes (radio buttons)
- **Risk/Reward target:** 1:1, 1.5:1, 2:1 (radio buttons)
- **Breakout confirmation:** "Candle close above range" (default, fewer false signals) vs "Any tick above range" (faster, more signals)
- **Signal filters:**
  - Max risk per share ($) — default $2.00
  - Min range width ($) — default $0.15
  - Max range as % of price — default 0.5%
  - Min volume ratio vs average — default 50%
- **Discord webhook URL:** text input with test button
- **Engine control:** start/stop toggle, status indicator

## Data Model

### Tables

**signals**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| ticker | TEXT | e.g., "SPY" |
| date | TEXT | Trading date (YYYY-MM-DD) |
| direction | TEXT | "LONG" or "SHORT" |
| candle_size | INTEGER | 5, 15, or 30 |
| range_high | REAL | Opening range high |
| range_low | REAL | Opening range low |
| range_width | REAL | High minus low |
| entry_price | REAL | Breakout price |
| stop_price | REAL | Stop loss price |
| target_price | REAL | Target price |
| risk_reward | REAL | R/R ratio used |
| signal_time | TEXT | ISO timestamp |
| outcome | TEXT | "WIN", "LOSS", "OPEN", or NULL |
| outcome_time | TEXT | When outcome was determined |
| outcome_price | REAL | Price at outcome |
| max_favorable | REAL | Best price in signal direction |
| max_adverse | REAL | Worst price against signal |
| skipped | INTEGER | 1 if signal was filtered out, 0 otherwise |
| skip_reason | TEXT | Why signal was skipped (NULL if not skipped) |

**opening_ranges**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| ticker | TEXT | e.g., "SPY" |
| date | TEXT | Trading date |
| candle_size | INTEGER | Minutes |
| range_high | REAL | High of first candle |
| range_low | REAL | Low of first candle |
| open_price | REAL | Market open price |
| close_price | REAL | First candle close |
| volume | INTEGER | First candle volume |

**settings**
| Column | Type | Description |
|--------|------|-------------|
| key | TEXT PK | Setting name |
| value | TEXT | JSON-encoded value |

Settings keys: `watchlist`, `candle_size`, `risk_reward`, `breakout_mode`, `discord_webhook_url`, `max_risk_per_share`, `min_range_width`, `max_range_pct`, `min_volume_ratio`.

## Stack

- **Signal Engine:** Node.js, TypeScript, @alpacahq/alpaca-trade-api (WebSocket), better-sqlite3, node-cron
- **Web Dashboard:** Next.js (App Router), TypeScript, Tailwind CSS
- **Database:** SQLite via better-sqlite3
- **Alerts:** Discord webhook (simple HTTP POST, no bot token needed)
- **UI Theme:** Dark theme matching PolySignal (#131722 backgrounds, #00c853 green, #ff3d00 red, #4f8fea blue accent)

## Deployment

- **Signal Engine:** Railway (always-on container) or PM2 on a home machine / VPS
- **Web Dashboard:** Vercel
- **Database:** SQLite file on the engine's host (dashboard reads via API routes that proxy to the engine, or shared filesystem if co-located)

For simplest setup: run both services on the same machine (Railway or VPS) so they share the SQLite file directly.

## Scope Boundaries

**In scope (v1):**
- Signal engine with Alpaca WebSocket integration
- Opening range construction (5/15/30 min configurable)
- Breakout detection with 1-min candle confirmation
- Discord webhook alerts (session start, range set, breakout, daily summary)
- Outcome tracking (win/loss/open)
- Web dashboard: live view, history with stats, settings
- SQLite storage
- Dark theme UI

**Out of scope (v1, could add later):**
- Trade execution
- Backtesting against historical data
- Multiple alert channels (SMS, Telegram, email)
- Pre-market range analysis (gap up/down detection)
- Volume confirmation filters
- Multi-user support
- Mobile app (responsive web is sufficient)
