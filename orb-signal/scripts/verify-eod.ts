/**
 * Verify hold-to-EOD exit prices against real market closes.
 * Hypothesis: the EOD flatten recorded exit==entry (a fallback) instead of the
 * true ~15:55 ET price, masking the real P&L of held trades.
 */
import { ALPACA_REST_URL } from "../src/lib/constants";
import { getDb } from "../src/lib/db/index";
import type { AlpacaBar } from "../src/lib/types";

function headers() {
  return { "APCA-API-KEY-ID": process.env.ALPACA_API_KEY!, "APCA-API-SECRET-KEY": process.env.ALPACA_API_SECRET! };
}
function etOffset(d: Date) { const m = d.getUTCMonth(); return (m > 2 && m < 10) ? 4 : (m === 2 || m === 10) ? 4 : 5; }
function minuteET(b: AlpacaBar) { const d = new Date(b.t); return (d.getUTCHours() - etOffset(d)) * 60 + d.getUTCMinutes(); }

async function closeAt1555(ticker: string, date: string): Promise<number | null> {
  const params = new URLSearchParams({
    symbols: ticker, timeframe: "1Min",
    start: `${date}T15:50:00-04:00`, end: `${date}T16:00:00-04:00`,
    limit: "20", feed: "iex", sort: "asc",
  });
  const res = await fetch(`${ALPACA_REST_URL}/v2/stocks/bars?${params}`, { headers: headers() });
  if (!res.ok) return null;
  const data = await res.json();
  const bars: AlpacaBar[] = data.bars?.[ticker] ?? [];
  // last bar at/before 15:55
  const upto = bars.filter(b => minuteET(b) <= 955);
  const pick = upto.length ? upto[upto.length - 1] : bars[bars.length - 1];
  return pick ? pick.c : null;
}

async function main() {
  const db = getDb();
  const eod = db.prepare(`
    SELECT id, date, ticker, direction, entry_price, stop_price, exit_price, r_multiple, risk
    FROM signals WHERE timeframe=5 AND was_selected=1 AND exit_type='eod' AND date>='2026-06-15'
    ORDER BY date
  `).all() as any[];

  console.log("TICK  DIR    DATE        ENTRY    RECORDED  REAL~1555  RECORDED-R  TRUE-R   DELTA");
  let recordedSum = 0, trueSum = 0;
  const corrections: { id: number; trueR: number; realClose: number }[] = [];
  for (const t of eod) {
    const real = await closeAt1555(t.ticker, t.date);
    if (real === null) { console.log(`${t.ticker} ${t.date} — no data`); continue; }
    const truePnl = t.direction === "LONG" ? real - t.entry_price : t.entry_price - real;
    const trueR = t.risk > 0 ? truePnl / t.risk : 0;
    recordedSum += t.r_multiple; trueSum += trueR;
    corrections.push({ id: t.id, trueR, realClose: real });
    console.log(
      `${t.ticker.padEnd(5)} ${t.direction.padEnd(5)} ${t.date}  ${t.entry_price.toFixed(2).padStart(7)}  ${t.exit_price.toFixed(2).padStart(7)}   ${real.toFixed(2).padStart(7)}    ${(t.r_multiple>=0?"+":"")}${t.r_multiple.toFixed(2)}      ${(trueR>=0?"+":"")}${trueR.toFixed(2)}   ${(trueR-t.r_multiple>=0?"+":"")}${(trueR-t.r_multiple).toFixed(2)}`
    );
  }
  console.log("─".repeat(78));
  console.log(`Recorded EOD total: ${recordedSum.toFixed(2)}R | True EOD total: ${trueSum.toFixed(2)}R | Delta: ${(trueSum-recordedSum>=0?"+":"")}${(trueSum-recordedSum).toFixed(2)}R`);
  console.log(`\nIf this delta is large and nonzero, the EOD flatten is mis-recording exits.`);

  if (process.argv.includes("--fix")) {
    const upd = db.prepare(`UPDATE signals SET exit_price=?, r_multiple=?, outcome=? WHERE id=?`);
    for (const c of corrections) {
      const outcome = c.trueR > 0.2 ? "WIN" : c.trueR < -0.2 ? "LOSS" : "SCRATCH";
      upd.run(c.realClose, c.trueR, outcome, c.id);
    }
    console.log(`\n[--fix] Backfilled ${corrections.length} EOD trades with true closing prices.`);
  }
}
main().catch(console.error);
