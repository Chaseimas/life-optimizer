# ORB Signal Dashboard — Design Spec

An automated Opening Range Breakout signal tool that monitors US stocks at market open, detects breakouts with professional-grade filters, and alerts via Discord.

## Overview

**What:** A background signal engine + web dashboard that implements the ORB (Opening Range Breakout) day trading strategy the way real day traders use it — with VWAP alignment, trend filters, candle quality checks, partial profit targets, and trailing stops. It connects to Alpaca's real-time data at market open, builds the opening range, monitors for high-quality breakouts, sends Discord alerts, and tracks outcomes over time.

**Who:** Built for personal use. User is away from screens at market open — the tool must be fully autonomous during market hours.

**What it does NOT do:** Execute trades. It identifies signals and alerts the user, who decides whether to act.

## The ORB Strategy (Full Rules)

### Phase 1: Pre-Market Context (9:00–9:30 AM ET)

Before the opening range even forms, the engine gathers context:

- **Prior day levels:** Yesterday's high, low, and close. These are key support/resistance zones that often act as magnets or barriers for breakouts.
- **Overnight high/low:** The high and low from the after-hours and pre-market session (4:00 PM prior day → 9:30 AM today). Breakouts that align with overnight direction are stronger.
- **Pre-market gap:** The difference between today's pre-market price and yesterday's close. Gap direction significantly affects ORB — long breakouts on gap-up days hit targets ~74% of the time vs ~48% on gap-down days.
- **Daily trend (20-day SMA):** Is the stock above or below its 20-day simple moving average? This is the higher-timeframe trend filter. Only take longs if price is above the 20-day SMA; only take shorts if below. This single filter significantly reduces counter-trend failures.
- **14-day ATR:** Average True Range over the last 14 trading days. Used to judge whether the opening range is normal-sized or abnormally wide/tight for this ticker.

### Phase 2: Opening Range Construction (9:30 AM → candle close)

- Market opens at 9:30 AM ET
- Track the highest high and lowest low during the first candle (configurable: 5, 15, or 30 minutes; default 15 min — the most common timeframe among real ORB traders, balancing speed vs false breakout rate)
- When the candle closes, the range is locked: `range_high` and `range_low`
- Also record: opening range volume, VWAP at range close, open price

### Phase 3: Signal Quality Gate

Not every opening range produces a tradeable setup. The engine runs these checks before monitoring for breakouts. If any check fails, that ticker is marked "no trade today" with the reason logged.

**Filters (all must pass):**

1. **Trend alignment (20-day SMA):** Long signals require price above the 20-day SMA. Short signals require price below it. Counter-trend breakouts fail far more often than they succeed.

2. **Range vs ATR:** Compare range width to 14-day ATR. Skip if range > 75% of ATR — the daily move is already mostly spent, not enough room for the breakout to run. Grade the setup:
   - **A:** Range < 40% of ATR (plenty of room)
   - **B:** Range 40–60% of ATR (decent)
   - **C:** Range 60–75% of ATR (borderline)

3. **Range as % of price:** Skip if range width > 0.8% of the stock price (wild, choppy open) or < 0.05% (too tight, noise-level range).

4. **Volume check:** Skip if opening range candle volume is below 50% of the ticker's trailing 10-day average first-candle volume. Low volume ranges are unreliable.

5. **Breakout room score:** Remaining ATR (ATR minus range width) must be greater than the range width. If there's less room to run than you're risking, the reward doesn't justify the stop distance.

### Phase 4: Breakout Detection (candle close → 11:30 AM ET)

After the range is locked and passes the quality gate:

- Monitor each **1-minute candle close** (not intra-candle ticks — candle close confirmation reduces false breakouts)
- **Long breakout conditions (ALL must be true):**
  - 1-min candle closes above `range_high`
  - Candle close is in the **top 30%** of the candle's range (strong close, not a wick that barely poked above)
  - Price is **above VWAP** (aligned with the day's flow of money)
  - Breakout candle volume is above the average 1-min volume for this ticker (conviction behind the move)
- **Short breakout conditions (ALL must be true):**
  - 1-min candle closes below `range_low`
  - Candle close is in the **bottom 30%** of the candle's range
  - Price is **below VWAP**
  - Breakout candle volume is above average

**One trade per day (global).** The engine takes exactly ONE trade across all tickers, all directions. Once a signal fires, the engine stops looking for new breakouts and focuses entirely on tracking that one position. If it loses, the day is done — no revenge trading, no "let me try another ticker." Discipline is the edge.

**How the engine picks the best trade:**

When multiple tickers pass all filters and break out around the same time, the engine ranks them by a composite score:

1. **Grade weight** — A = 3 pts, B = 2 pts, C = 1 pt
2. **Gap alignment** — signal direction matches gap = +2 pts; against gap = -1 pt
3. **VWAP distance** — further above VWAP for longs (below for shorts) = stronger conviction, +0 to 2 pts scaled
4. **Breakout volume** — higher relative volume on the breakout candle = more conviction, +0 to 2 pts scaled
5. **Breakout candle quality** — close position within the candle range, closer to the extreme = stronger, +0 to 1 pt scaled

The highest-scoring setup wins. If two tickers break out minutes apart, the engine waits up to 2 minutes after the first valid breakout to see if a better one fires on another ticker. After 2 minutes (or if only one ticker qualifies), it commits to the best one and sends the alert.

If nothing qualifies all day, the engine posts "No trade today" at 11:30 AM. That's a valid outcome — the best trade is sometimes no trade.

**Time cutoff: 11:30 AM ET.** No new signals after this. Late breakouts are thin-market traps. The engine continues monitoring the active position (if any) for outcome tracking, but won't open new ones.

### Phase 5: Exit Levels & Outcome Tracking

One trade, one position — exit strategy is clean and simple:

**Stop loss:** The opposite end of the opening range. For a long, stop = range low. For a short, stop = range high. This is the max risk on the trade. Configurable to use mid-range for a tighter stop (higher R potential but more frequent stops).

**Target (measured move):** The range height projected from the breakout point. For a long: `entry_price + range_width`. For a short: `entry_price - range_width`. This is the primary profit target — a 1:1 R trade.

**Trailing stop (after target hit):** Once the target is reached, the alert notifies you. If you're still in, the suggested stop moves to breakeven (entry price). From there, it trails below the 9-period EMA on the 5-minute chart for longs (above for shorts), letting you ride trend days for bonus profit beyond the initial target.

**Failure exit:** If a 1-minute candle **closes back inside the opening range** after entry, the breakout has failed. Get out — don't wait for the full stop. This saves you from giving back the full range width on a clear rejection.

**Time exit:** If neither target nor stop is hit within 2 hours of entry, the trade is going nowhere. Log it as a scratch and move on.

**End of day (4:00 PM):** If still open (rare with the above rules), close at market price.

**Outcome categories:**
- **WIN** — hit target or trailed out above entry
- **LOSS** — hit stop or failure exit below entry
- **SCRATCH** — time exit or EOD close near entry (< 0.2R either direction)

### Phase 6: Gap Context in Alerts

The engine includes gap context in every alert because it materially affects expected win rate:

- **Gap-up + Long breakout** → highest probability setup (~74% target hit rate)
- **Gap-down + Short breakout** → second-best (gap continuation)
- **Gap-up + Short breakout** → counter-gap, lower probability
- **Gap-down + Long breakout** → counter-gap, lowest probability (~48%)

The alert shows gap direction and whether the signal is with or against the gap.

## Architecture

Two services:

### 1. Signal Engine (Node.js background service)

The always-on process that does the real work:

- **Pre-market (9:00 AM ET):** Fetches prior day levels, overnight high/low, pre-market price, 20-day SMA, and 14-day ATR for all configured tickers via Alpaca REST API. Calculates gap direction and size.
- **Session start (9:25 AM ET):** Connects to Alpaca WebSocket for real-time bars. Posts "Session starting" to Discord with watchlist and context.
- **Opening range phase (9:30 → candle close):** Streams real-time bars, tracks high/low of the first candle. Tracks VWAP. When the candle closes, locks in the opening range. Runs the quality gate. Posts range + quality assessment to Discord.
- **Breakout monitoring (candle close → 11:30 AM):** Watches 1-min candle closes against range boundaries. Checks all breakout conditions (candle quality, VWAP alignment, volume). On valid breakout, fires Discord alert with full context.
- **Position tracking (breakout → 4:00 PM):** For each active signal, monitors price against Target 1, Target 2, stop, failure condition, and trailing stop. Fires Discord updates on partial profit, trailing stop moves, and exits.
- **End of day (4:00 PM):** Closes any remaining open signals. Calculates final outcomes. Posts daily summary to Discord.
- **Post-market:** Disconnects WebSocket, sleeps until next trading day.

### 2. Web Dashboard (Next.js)

A lightweight web app for visibility and configuration:

- **Live View** — today's opening ranges, breakout status, key levels, and active signal P/L
- **History** — past signals with outcomes, win rates, performance stats, grade analysis
- **Settings** — manage watchlist, strategy parameters, filters, Discord webhook

### 3. SQLite Database

Shared between both services. Single user, moderate data volume — SQLite is the right fit.

## Discord Alerts

Uses a simple webhook (no bot needed). Message types:

**Session start (9:25 AM):**
```
📊 ORB Session Starting
Watching: SPY, QQQ, AAPL
Candle: 15 min | Trend filter: ON
SPY: above 20-SMA ✅ | gap +0.3% ↑
QQQ: above 20-SMA ✅ | gap +0.1% ↑
AAPL: below 20-SMA ⚠️ (shorts only)
```

**Range established (after first candle closes):**
```
📐 SPY Opening Range Set  [A]
High: $543.10 | Low: $542.30 | Width: $0.80
VWAP: $542.85 | ATR: $3.20 (range = 25%)
Volume: 1.8M (142% of avg) ✅
Prior day H/L: $544.50 / $540.20
Watching for breakout until 11:30 AM...
```

**Today's trade (breakout signal):**
```
🟢 ORB LONG — SPY  [A]  ⭐ BEST SETUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Entry:   $543.12
Stop:    $542.30 (range low)
Target:  $543.92 (measured move, 1R)
Risk:    $0.82/share
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Above VWAP ($542.85)
✅ Trend: above 20-SMA
✅ Gap: +0.3% (with gap — high probability)
✅ Breakout vol: 185% of avg
✅ Ranked #1 of 2 valid setups
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This is today's ONE trade. Day is done after this.
Time: 9:47 AM ET
```

**Target hit:**
```
🎯 SPY LONG — Target hit at $543.92 (+$0.80, 1R)
Stop moved to breakeven ($543.12).
Trail below 9-EMA if you're riding the runner.
```

**Trade closed:**
```
🏁 SPY LONG — Done.
Exit: $544.35 (trailed out above target)
Result: +$1.23/share (1.5R) ✅ WIN
Day is complete.
```

**No trade today (11:30 AM):**
```
🚫 No trade today.
No setup passed all filters. Sitting out is the right call.
SPY: range too wide (82% of ATR)
QQQ: below VWAP at breakout
AAPL: no breakout before cutoff
```

**Daily summary (4:00 PM):**
```
📋 ORB Daily Summary — Jun 9
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Trade: SPY 🟢 LONG [A] → ✅ WIN
Entry $543.12 → Exit $544.35
Result: +$1.23/share (1.5R)
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Also qualified: QQQ (not taken, ranked #2)
Skipped: AAPL (below VWAP)
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Running: 58% win rate (23W-17L)
Grade A signals: 68% win rate
Streak: 3W
```

## Web Dashboard Detail

### Live View (home page)

Per-ticker cards showing:
- **Opening range** as a visual bar (low—high) with current price marker, VWAP line, and prior day levels overlaid
- **Key levels:** prior day H/L, overnight H/L, VWAP — all drawn on the range bar
- **Status badge:** "Pre-market" → "Building range…" → "Watching…" → "LONG [A] ✅" / "SHORT [B] 🔴" / "Skipped" / "No breakout" / "Past cutoff"
- **Filters summary:** trend (✅/⚠️), VWAP position, gap direction, volume status
- **Signal details** (if triggered): entry, stop, target, current P/L, trailing stop level
- **Time info:** time since open, time since signal, time until cutoff

Top bar shows: market status (pre-market / open / past cutoff / closed), tickers watched, today's trade status ("Waiting for setup" / "SPY LONG active" / "Done — WIN +$1.23" / "No trade today").

### History Page

- **Summary stats at top:** total signals, win rate, average R, best streak, worst streak, profit factor, win rate by grade (A/B/C)
- **Filterable table:** date, ticker, direction, grade, entry, stop, target, outcome, R multiple, exit type, duration, gap context, ranking score
- **Filters:** ticker, direction, outcome, grade, exit type, date range
- **Per-ticker breakdown:** which tickers have the best ORB win rate
- **Grade analysis:** win rate and average R broken down by A/B/C grade — validates whether the grading system works

### Settings Page

**Strategy:**
- Watchlist: add/remove tickers
- Candle size: 5 / 15 / 30 minutes (default 15)
- Stop placement: full range (default) or mid-range (tighter stop, higher R but more stops hit)

**Filters:**
- Trend filter (20-SMA): ON/OFF (default ON)
- VWAP alignment: ON/OFF (default ON)
- Candle close quality (top/bottom 30%): ON/OFF (default ON)
- Volume on breakout candle: ON/OFF (default ON)
- Max range vs ATR: default 75%
- Max range as % of price: default 0.8%
- Min range as % of price: default 0.05%
- Min opening range volume ratio: default 50%
- Time cutoff: default 11:30 AM ET

**Exits:**
- Target: measured move / 1R (default — clean 1:1 risk/reward)
- Trailing stop after target: 9-EMA (default) or VWAP
- Failure exit (close back inside range): ON/OFF (default ON)
- Time exit (2 hours): ON/OFF (default ON)

**Discipline:**
- Trades per day: 1 (hardcoded — this is the core philosophy)
- Selection delay: 2 minutes (wait after first valid breakout to see if a better ticker qualifies)

**Alerts:**
- Discord webhook URL with test button
- Alert on skipped signals: ON/OFF (default ON)
- Alert on signal updates (T1 hit, trailing): ON/OFF (default ON)

**Engine:**
- Start/stop toggle, status indicator

## Data Model

### Tables

**signals**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| ticker | TEXT | e.g., "SPY" |
| date | TEXT | Trading date (YYYY-MM-DD) |
| direction | TEXT | "LONG" or "SHORT" |
| grade | TEXT | "A", "B", "C", or NULL (if skipped) |
| candle_size | INTEGER | 5, 15, or 30 |
| range_high | REAL | Opening range high |
| range_low | REAL | Opening range low |
| range_width | REAL | High minus low |
| entry_price | REAL | Breakout candle close |
| stop_price | REAL | Stop loss price |
| target_price | REAL | Measured move target (1R) |
| risk_per_share | REAL | Range width (or half if mid-range stop) |
| signal_time | TEXT | ISO timestamp |
| vwap_at_entry | REAL | VWAP at time of breakout |
| breakout_candle_vol | INTEGER | Volume of the breakout candle |
| breakout_candle_quality | REAL | Where close falls in candle range (0.0–1.0) |
| outcome | TEXT | "WIN", "LOSS", "SCRATCH", or NULL |
| exit_type | TEXT | "target", "stop", "trail", "failure", "time", "eod" |
| exit_price | REAL | Price at exit |
| exit_time | TEXT | When position was exited |
| r_multiple | REAL | Actual R achieved (profit / risk) |
| target_hit | INTEGER | 1 if target was reached, 0 if not |
| ranking_score | REAL | Composite score used to pick this as today's trade |
| was_selected | INTEGER | 1 if this was today's chosen trade, 0 if it qualified but wasn't picked |
| max_favorable | REAL | Best price in signal direction |
| max_adverse | REAL | Worst price against signal |
| skipped | INTEGER | 1 if filtered out, 0 otherwise |
| skip_reason | TEXT | Why skipped (NULL if not skipped) |
| range_atr_pct | REAL | Range width as % of ATR |
| gap_pct | REAL | Pre-market gap as % of prior close |
| gap_aligned | INTEGER | 1 if signal direction matches gap, 0 if against |
| trend_aligned | INTEGER | 1 if signal aligns with 20-SMA, 0 if not |

**opening_ranges**
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| ticker | TEXT | e.g., "SPY" |
| date | TEXT | Trading date |
| candle_size | INTEGER | Minutes |
| range_high | REAL | High of first candle |
| range_low | REAL | Low of first candle |
| range_width | REAL | High minus low |
| open_price | REAL | Market open price |
| close_price | REAL | First candle close |
| volume | INTEGER | First candle volume |
| vwap_at_close | REAL | VWAP when range candle closed |
| atr_14 | REAL | 14-day ATR for this ticker |
| sma_20 | REAL | 20-day SMA for this ticker |
| prior_day_high | REAL | Yesterday's high |
| prior_day_low | REAL | Yesterday's low |
| prior_day_close | REAL | Yesterday's close |
| overnight_high | REAL | Overnight session high |
| overnight_low | REAL | Overnight session low |
| premarket_price | REAL | Price just before 9:30 open |
| gap_pct | REAL | Gap size as % of prior close |
| gap_direction | TEXT | "UP", "DOWN", or "FLAT" |
| quality_grade | TEXT | "A", "B", "C", or "SKIP" |
| skip_reason | TEXT | Why skipped (NULL if tradeable) |

**settings**
| Column | Type | Description |
|--------|------|-------------|
| key | TEXT PK | Setting name |
| value | TEXT | JSON-encoded value |

Settings keys: `watchlist`, `candle_size`, `stop_placement`, `trend_filter`, `vwap_filter`, `candle_quality_filter`, `breakout_volume_filter`, `max_range_atr_pct`, `max_range_price_pct`, `min_range_price_pct`, `min_volume_ratio`, `time_cutoff`, `selection_delay_sec`, `trailing_stop_method`, `failure_exit`, `time_exit`, `discord_webhook_url`, `alert_skipped`, `alert_updates`.

## Stack

- **Signal Engine:** Node.js, TypeScript, @alpacahq/alpaca-trade-api (WebSocket + REST for historical data), better-sqlite3, node-cron
- **Web Dashboard:** Next.js (App Router), TypeScript, Tailwind CSS
- **Database:** SQLite via better-sqlite3
- **Alerts:** Discord webhook (simple HTTP POST, no bot token needed)
- **UI Theme:** Dark theme matching PolySignal (#131722 backgrounds, #00c853 green, #ff3d00 red, #4f8fea blue accent)

## Deployment

- **Signal Engine:** Railway (always-on container) or PM2 on a home machine / VPS
- **Web Dashboard:** Vercel
- **Database:** SQLite file on the engine's host

For simplest setup: run both services on the same machine (Railway or VPS) so they share the SQLite file directly.

## Scope Boundaries

**In scope (v1):**
- Signal engine with Alpaca WebSocket + REST integration
- Pre-market context gathering (prior day levels, overnight H/L, gap, 20-SMA, ATR)
- Opening range construction (5/15/30 min configurable, default 15)
- Full signal quality gate (trend, VWAP, ATR, volume, range %)
- Breakout detection with candle close quality + VWAP + volume confirmation
- One-trade-per-day discipline with composite ranking to pick the single best setup
- Clean exit system (target, stop, trailing stop, failure exit, time exit)
- One-and-done rule, 11:30 AM time cutoff
- Quality grading (A/B/C) with grade-based performance tracking
- Gap context in alerts and outcome analysis
- Discord webhook alerts (session start, range, breakout, updates, exits, skips, daily summary)
- Web dashboard: live view with key levels, history with grade analysis, settings
- SQLite storage
- Dark theme UI

**Out of scope (v1, could add later):**
- Trade execution
- Backtesting against historical data
- Multiple alert channels (SMS, Telegram, email)
- Relative strength / sector rotation analysis
- Multi-user support
- Mobile app (responsive web is sufficient)
