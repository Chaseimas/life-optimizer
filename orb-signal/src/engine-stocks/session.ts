/**
 * Stock ORB paper-trading session.
 *
 * Strategy (Zarattini-style, walk-forward validated):
 *  - 5-min opening range (9:30-9:35 ET), timestamp-verified
 *  - Trade only in the direction of the first 5-min candle
 *  - Enter on first 1-min close beyond the range, before 10:30 ET
 *  - Stop = opposite side of range, target = 3R, otherwise hold to EOD
 *  - No breakeven stop, no trailing — bracket order does the work
 *  - Flatten everything at 3:55 PM ET
 *
 * Orders are REAL paper orders on Alpaca — fills, slippage, and P&L are tracked.
 */

import { STOCKS_CONFIG as CFG } from "./config";
import * as alpaca from "./alpaca";
import * as alerts from "./alerts";
import { acquireSessionLock, releaseSessionLock } from "./lock";
import { insertSignal, updateSignalOutcome } from "@/lib/db/queries/signals";
import type { AlpacaBar, Direction } from "@/lib/types";

interface TickerState {
  ticker: string;
  rangeHigh: number;
  rangeLow: number;
  rangeWidth: number;
  direction: Direction | null;
  skipped: string | null;
  entered: boolean;
}

interface ActiveTrade {
  dbId: number;
  ticker: string;
  direction: Direction;
  qty: number;
  signalPrice: number;     // 1-min close that triggered entry
  fillPrice: number;
  stopPrice: number;
  targetPrice: number;
  riskPerShare: number;
  entryOrderId: string;
  tpLegId: string | null;
  slLegId: string | null;
  closed: boolean;
  rMultiple: number;
  exitType: string;
  exitPrice: number;
}

function etOffset(d: Date): number {
  const m = d.getUTCMonth(), day = d.getUTCDate();
  if (m < 2 || m > 10) return 5;
  if (m > 2 && m < 10) return 4;
  if (m === 2) return day >= 9 ? 4 : 5;
  return day < 2 ? 4 : 5;
}

function nowETMinutes(): number {
  const d = new Date();
  return (d.getUTCHours() - etOffset(d)) * 60 + d.getUTCMinutes() + d.getUTCSeconds() / 60;
}

function minuteET(bar: AlpacaBar): number {
  const d = new Date(bar.t);
  return (d.getUTCHours() - etOffset(d)) * 60 + d.getUTCMinutes();
}

function todayET(): { dateStr: string; sessionStartISO: string } {
  const now = new Date();
  const off = etOffset(now);
  const et = new Date(now.getTime() - off * 3600000);
  const y = et.getUTCFullYear(), m = et.getUTCMonth(), d = et.getUTCDate();
  const dateStr = et.toISOString().split("T")[0];
  const sessionStartISO = new Date(Date.UTC(y, m, d, 9 + off, 30, 0)).toISOString();
  return { dateStr, sessionStartISO };
}

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

export async function runStockSession(): Promise<void> {
  const { dateStr, sessionStartISO } = todayET();
  console.log(`[stocks] Session start for ${dateStr}`);

  // Single-instance guard: only one session may run per day. Prevents the
  // 2026-06-22 incident where multiple concurrent processes stacked duplicate
  // orders into naked oversized positions.
  if (!acquireSessionLock(dateStr)) {
    console.log("[stocks] Another session already running today — exiting (single-instance lock).");
    return;
  }

  try {
  // Holiday / weekend check via Alpaca clock
  try {
    const clock = await alpaca.getClock();
    if (!clock.is_open) {
      const nextOpenET = new Date(new Date(clock.next_open).getTime() - etOffset(new Date()) * 3600000);
      if (nextOpenET.toISOString().split("T")[0] !== dateStr) {
        console.log("[stocks] Market closed today (holiday/weekend). Exiting.");
        return;
      }
    }
  } catch (err) {
    console.error("[stocks] Clock check failed:", err);
    await alerts.alertError(`Clock check failed: ${err}`);
    return;
  }

  // Optional MWF filter
  if (CFG.MWF_ONLY) {
    const dow = new Date(dateStr + "T12:00:00Z").getUTCDay();
    if (dow !== 1 && dow !== 3 && dow !== 5) {
      console.log("[stocks] MWF_ONLY set and today is Tue/Thu. Exiting.");
      return;
    }
  }

  const account = await alpaca.getAccount();
  const equity = parseFloat(account.equity);
  console.log(`[stocks] Paper equity: $${equity.toFixed(0)}`);

  // Wait until ranges can be built (9:35:20 ET, small buffer for bar availability)
  const rangeReadyMin = 9 * 60 + 35 + 20 / 60;
  while (nowETMinutes() < rangeReadyMin) {
    await sleep(5000);
  }

  // ── Build ranges ──
  const states = new Map<string, TickerState>();
  {
    const barsBySym = await alpaca.getTodayBars([...CFG.TICKERS], sessionStartISO);
    for (const ticker of CFG.TICKERS) {
      const bars = barsBySym.get(ticker) ?? [];
      const st: TickerState = {
        ticker, rangeHigh: 0, rangeLow: 0, rangeWidth: 0,
        direction: null, skipped: null, entered: false,
      };

      // Timestamp-true ORB: need bars at exactly 9:30..9:34
      const first5: AlpacaBar[] = [];
      for (let i = 0; i < CFG.ORB_MINUTES; i++) {
        const b = bars.find(x => minuteET(x) === 570 + i);
        if (!b) break;
        first5.push(b);
      }

      if (first5.length < CFG.ORB_MINUTES) {
        st.skipped = `sparse open (${first5.length}/5 bars)`;
      } else {
        st.rangeHigh = Math.max(...first5.map(b => b.h));
        st.rangeLow = Math.min(...first5.map(b => b.l));
        st.rangeWidth = st.rangeHigh - st.rangeLow;
        const body = Math.abs(first5[CFG.ORB_MINUTES - 1].c - first5[0].o);
        if (st.rangeWidth <= 0) {
          st.skipped = "zero range";
        } else if (body < st.rangeWidth * CFG.MIN_BODY_FRAC) {
          st.skipped = "indecisive candle";
        } else {
          st.direction = first5[CFG.ORB_MINUTES - 1].c > first5[0].o ? "LONG" : "SHORT";
          if (CFG.DIR_FILTER && !CFG.DIR_FILTER.includes(`${ticker} ${st.direction}`)) {
            st.skipped = `direction filtered (${st.direction})`;
            st.direction = null;
          }
        }
      }
      states.set(ticker, st);
    }

    await alerts.alertSessionStart(equity, [...states.values()].map(s => ({
      ticker: s.ticker, high: s.rangeHigh, low: s.rangeLow,
      dir: s.direction, skipped: s.skipped,
    })));
    console.log(`[stocks] Ranges set: ${[...states.values()].filter(s => !s.skipped).length} watchable, ${[...states.values()].filter(s => s.skipped).length} skipped`);
  }

  // ── Main loop ──
  const active: ActiveTrade[] = [];
  let dayR = 0;

  while (nowETMinutes() < CFG.FLATTEN_MIN) {
    const nowMin = nowETMinutes();

    try {
      // 1) Entries (only before cutoff)
      if (nowMin <= CFG.ENTRY_CUTOFF_MIN + 1) {
        const barsBySym = await alpaca.getTodayBars([...CFG.TICKERS], sessionStartISO);

        for (const st of states.values()) {
          if (st.skipped || st.entered || !st.direction) continue;
          if (dayR <= -CFG.DAILY_LOSS_LIMIT_R) break;
          if (active.filter(t => !t.closed).length >= CFG.MAX_CONCURRENT) break;

          const bars = barsBySym.get(st.ticker) ?? [];
          // First 1-min close beyond range in candle direction, within window
          const sigBar = bars.find(b => {
            const m = minuteET(b);
            if (m < 575 || m > CFG.ENTRY_CUTOFF_MIN) return false;
            return st.direction === "LONG" ? b.c > st.rangeHigh : b.c < st.rangeLow;
          });
          if (!sigBar) continue;

          // Freshness guard: if the engine was offline (sleep/restart) and the
          // breakout happened more than 3 minutes ago, entering now at market
          // would be a different trade than the strategy. Skip the day instead.
          if (nowETMinutes() - minuteET(sigBar) > 3) {
            st.entered = true;
            st.skipped = "signal missed (engine offline at breakout)";
            console.log(`[stocks] ${st.ticker}: breakout at ${Math.floor(minuteET(sigBar) / 60)}:${String(minuteET(sigBar) % 60).padStart(2, "0")} ET missed — too stale to enter.`);
            continue;
          }

          st.entered = true;
          const trade = await enterTrade(st, sigBar.c, equity, dateStr);
          if (trade) active.push(trade);
        }
      }

      // 2) Exit detection — poll bracket legs
      for (const t of active) {
        if (t.closed) continue;
        const exit = await checkLegFill(t);
        if (exit) {
          t.closed = true;
          t.exitType = exit.type;
          t.exitPrice = exit.price;
          const pnlPerShare = t.direction === "LONG" ? exit.price - t.fillPrice : t.fillPrice - exit.price;
          t.rMultiple = t.riskPerShare > 0 ? pnlPerShare / t.riskPerShare : 0;
          dayR += t.rMultiple;
          recordExit(t);
          await alerts.alertExit({
            ticker: t.ticker, direction: t.direction, exitType: exit.type,
            fillPrice: t.fillPrice, exitPrice: exit.price,
            rMultiple: t.rMultiple, pnlDollars: pnlPerShare * t.qty,
          });
        }
      }

      // Nothing left to do today? Trust the broker, not our bookkeeping —
      // only stand down if Alpaca confirms the account is actually flat.
      if (nowMin > CFG.ENTRY_CUTOFF_MIN + 1 && active.every(t => t.closed)) {
        const positions = await alpaca.getPositions();
        if (positions.length === 0) {
          console.log("[stocks] Entry window over, account flat at broker. Standing down.");
          break;
        }
        console.log(`[stocks] Tracked trades closed but broker shows ${positions.length} position(s) — staying on watch until EOD.`);
      }
    } catch (err) {
      console.error("[stocks] Loop error:", err);
    }

    await sleep(CFG.POLL_SECONDS * 1000);
  }

  // ── EOD flatten ──
  // Always sweep, even if our bookkeeping says flat — an untracked position must
  // never survive the session (no-op when the account is already flat).
  try { await alpaca.closeAllPositions(); } catch { /* sweep is best-effort */ }

  const open = active.filter(t => !t.closed);
  if (open.length > 0) {
    console.log(`[stocks] 3:55 PM — flattening ${open.length} open position(s)`);
    try {
      await sleep(8000);
      const closedOrders = await alpaca.getClosedOrdersSince(sessionStartISO);

      for (const t of open) {
        // Find the closing fill: opposite side, filled after entry
        const closer = closedOrders.find(o =>
          o.symbol === t.ticker &&
          o.side === (t.direction === "LONG" ? "sell" : "buy") &&
          o.status === "filled" &&
          o.filled_avg_price &&
          o.id !== t.entryOrderId &&
          new Date(o.filled_at ?? 0).getTime() > Date.now() - 120000
        );
        // Exit price priority: real liquidation fill → actual market close → entry.
        // (Falling back to entry recorded held trades as flat +0.00R — masked +4R
        //  of real P&L over the 2026-06-15..18 week. Never fall back to entry if a
        //  market price is available.)
        let exitPrice: number;
        if (closer?.filled_avg_price) {
          exitPrice = parseFloat(closer.filled_avg_price);
        } else {
          const mkt = await alpaca.getLatestClose(t.ticker);
          exitPrice = mkt ?? t.fillPrice;
          if (mkt === null) console.error(`[stocks] ${t.ticker}: no fill and no market close — recording at entry (flat)`);
        }
        t.closed = true;
        t.exitType = "eod";
        t.exitPrice = exitPrice;
        const pnlPerShare = t.direction === "LONG" ? exitPrice - t.fillPrice : t.fillPrice - exitPrice;
        t.rMultiple = t.riskPerShare > 0 ? pnlPerShare / t.riskPerShare : 0;
        dayR += t.rMultiple;
        recordExit(t);
        await alerts.alertExit({
          ticker: t.ticker, direction: t.direction, exitType: "eod",
          fillPrice: t.fillPrice, exitPrice,
          rMultiple: t.rMultiple, pnlDollars: pnlPerShare * t.qty,
        });
      }
    } catch (err) {
      console.error("[stocks] Flatten error:", err);
      await alerts.alertError(`EOD flatten failed — check positions manually: ${err}`);
    }
  }

  // ── Summary ──
  const endAccount = await alpaca.getAccount().catch(() => null);
  const endEquity = endAccount ? parseFloat(endAccount.equity) : equity;
  await alerts.alertSummary({
    trades: active.map(t => ({ ticker: t.ticker, direction: t.direction, rMultiple: t.rMultiple, exitType: t.exitType })),
    dayR,
    dayPnl: endEquity - equity,
    equity: endEquity,
  });
  console.log(`[stocks] Session done. Day: ${dayR >= 0 ? "+" : ""}${dayR.toFixed(2)}R, equity $${endEquity.toFixed(0)}`);
  } finally {
    releaseSessionLock();
  }
}

async function enterTrade(
  st: TickerState,
  signalPrice: number,
  equity: number,
  dateStr: string,
): Promise<ActiveTrade | null> {
  const dir = st.direction!;
  const stopPrice = dir === "LONG" ? st.rangeLow : st.rangeHigh;
  const riskPerShareEst = Math.abs(signalPrice - stopPrice);
  if (riskPerShareEst <= 0) return null;

  // Size: 1% risk, capped by notional
  let qty = Math.floor((equity * CFG.RISK_PCT) / riskPerShareEst);
  qty = Math.min(qty, Math.floor((equity * CFG.MAX_NOTIONAL_PCT) / signalPrice));
  if (qty < 1) {
    console.log(`[stocks] ${st.ticker}: size 0 after caps (stop too tight vs notional cap). Skipped.`);
    return null;
  }

  const targetPrice = dir === "LONG"
    ? signalPrice + CFG.TARGET_R * riskPerShareEst
    : signalPrice - CFG.TARGET_R * riskPerShareEst;

  try {
    // Buying-power check: shorts consume ~1.5x margin, and a burst of simultaneous
    // brackets can outrun the account (learned 2026-06-11: SOXL rejected, two orders
    // queued unfilled). Size down to fit what's actually available.
    try {
      const acct = await alpaca.getAccount();
      const bp = parseFloat(acct.buying_power);
      const bpCapQty = Math.floor((bp / 1.6) / signalPrice);
      if (bpCapQty < qty) {
        console.log(`[stocks] ${st.ticker}: sized down ${qty} → ${bpCapQty} (buying power $${bp.toFixed(0)})`);
        qty = bpCapQty;
      }
      if (qty < 1) {
        console.log(`[stocks] ${st.ticker}: no buying power left. Skipped.`);
        return null;
      }
    } catch { /* if the check fails, proceed with notional-capped qty */ }

    const order = await alpaca.submitBracket({
      symbol: st.ticker,
      side: dir === "LONG" ? "buy" : "sell",
      qty,
      targetPrice,
      stopPrice,
    });

    // Wait for the market entry to fill
    let filled = order;
    for (let i = 0; i < 15 && filled.status !== "filled"; i++) {
      await sleep(2000);
      filled = await alpaca.getOrder(order.id);
    }
    if (filled.status !== "filled" || !filled.filled_avg_price) {
      // CRITICAL: cancel the order — an abandoned order that fills later becomes an
      // untracked position (happened 2026-06-11: TSLA and AMD filled after the engine
      // gave up and traded unmanaged). Cancel, then re-check once for the fill race.
      console.error(`[stocks] ${st.ticker}: entry not filled (${filled.status}) — canceling`);
      await alpaca.cancelOrder(order.id);
      await sleep(2000);
      filled = await alpaca.getOrder(order.id);
      if (filled.status !== "filled" || !filled.filled_avg_price) {
        await alerts.alertError(`${st.ticker} entry not filled (${filled.status}) — canceled safely`);
        return null;
      }
      // Lost the race — it filled anyway. Fall through and track it like a normal fill.
      console.log(`[stocks] ${st.ticker}: filled during cancel race — tracking it`);
    }

    const fillPrice = parseFloat(filled.filled_avg_price);
    const riskPerShare = Math.abs(fillPrice - stopPrice);
    const legs = filled.legs ?? [];
    const tpLeg = legs.find(l => l.type === "limit") ?? null;
    const slLeg = legs.find(l => l.type === "stop") ?? null;

    // Slippage in R: how much worse (positive) or better (negative) the fill was
    // vs the signal bar close, relative to the trade's risk
    const slippageDollars = (fillPrice - signalPrice) * (dir === "LONG" ? 1 : -1);
    const slippageR = riskPerShare > 0 ? slippageDollars / riskPerShare : 0;

    console.log(`[stocks] ENTRY ${st.ticker} ${dir} ${qty}@$${fillPrice.toFixed(2)} (signal $${signalPrice.toFixed(2)}, slippage ${slippageDollars.toFixed(3)} = ${slippageR.toFixed(3)}R)`);

    const dbId = insertSignal({
      ticker: st.ticker,
      date: dateStr,
      timeframe: 5,
      direction: dir,
      grade: "A",
      range_high: st.rangeHigh,
      range_low: st.rangeLow,
      range_width: st.rangeWidth,
      entry_price: fillPrice,
      stop_price: stopPrice,
      target_price: targetPrice,
      risk: riskPerShare,
      signal_time: new Date().toISOString(),
      vwap_at_entry: 0,
      breakout_volume_ratio: 0,
      breakout_candle_quality: 0,
      ranking_score: 0,
      was_selected: 1,
      range_atr_pct: 0,
      gap_pct: 0,
      gap_aligned: 0,
      trend_aligned: 1,
      sma_slope: 0,
      slippage_r: slippageR,
    });

    await alerts.alertEntry({
      ticker: st.ticker, direction: dir, qty,
      fillPrice, stopPrice, targetPrice,
      riskDollars: riskPerShare * qty,
    });

    return {
      dbId, ticker: st.ticker, direction: dir, qty,
      signalPrice, fillPrice, stopPrice, targetPrice, riskPerShare,
      entryOrderId: filled.id,
      tpLegId: tpLeg?.id ?? null,
      slLegId: slLeg?.id ?? null,
      closed: false, rMultiple: 0, exitType: "", exitPrice: 0,
    };
  } catch (err) {
    const msg = String(err);
    // Expected, benign rejections — log quietly, don't spam Discord:
    //  - "cannot be sold short": ticker not shortable today (borrow unavailable)
    //  - "must be entry orders": position already exists (shouldn't happen now
    //    that the session lock prevents concurrent runs, but handle defensively)
    if (msg.includes("cannot be sold short") || msg.includes("must be entry")) {
      console.log(`[stocks] ${st.ticker} ${dir}: skipped (${msg.includes("short") ? "not shortable today" : "position already exists"})`);
      return null;
    }
    console.error(`[stocks] ${st.ticker} order failed:`, err);
    await alerts.alertError(`${st.ticker} ${dir} order failed: ${msg.slice(0, 200)}`);
    return null;
  }
}

async function checkLegFill(t: ActiveTrade): Promise<{ type: string; price: number } | null> {
  try {
    if (t.tpLegId) {
      const tp = await alpaca.getOrder(t.tpLegId);
      if (tp.status === "filled" && tp.filled_avg_price) {
        return { type: "target", price: parseFloat(tp.filled_avg_price) };
      }
    }
    if (t.slLegId) {
      const sl = await alpaca.getOrder(t.slLegId);
      if (sl.status === "filled" && sl.filled_avg_price) {
        return { type: "stop", price: parseFloat(sl.filled_avg_price) };
      }
    }
  } catch (err) {
    console.error(`[stocks] Leg poll error for ${t.ticker}:`, err);
  }
  return null;
}

function recordExit(t: ActiveTrade): void {
  const outcome = t.rMultiple > 0.2 ? "WIN" : t.rMultiple < -0.2 ? "LOSS" : "SCRATCH";
  try {
    updateSignalOutcome(t.dbId, {
      outcome,
      exit_type: t.exitType,
      exit_price: t.exitPrice,
      exit_time: new Date().toISOString(),
      r_multiple: t.rMultiple,
      target_hit: t.exitType === "target" ? 1 : 0,
      max_favorable: t.exitPrice,
      max_adverse: t.exitPrice,
    });
  } catch (err) {
    console.error("[stocks] DB update error:", err);
  }
}
