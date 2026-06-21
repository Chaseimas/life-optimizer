import { getDb } from "../src/lib/db/index";

const db = getDb();
const STOCKS = ["TQQQ", "SOXL", "TSLA", "NVDA", "AMD", "AAPL", "PLTR", "MARA", "SMCI", "MSTR"];
const ph = STOCKS.map(() => "?").join(",");

const rows = db.prepare(`
  SELECT date,
    COUNT(*) n,
    SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) w,
    SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) l,
    SUM(CASE WHEN outcome='SCRATCH' THEN 1 ELSE 0 END) s,
    ROUND(SUM(r_multiple),2) dayR
  FROM signals
  WHERE timeframe=5 AND was_selected=1 AND ticker IN (${ph})
  GROUP BY date ORDER BY date
`).all(...STOCKS) as any[];

console.log("DATE         TRADES  W-L-S      DAY R");
console.log("─".repeat(45));
let cum = 0;
for (const r of rows) {
  cum += r.dayR;
  console.log(`${r.date}   ${String(r.n).padStart(2)}     ${r.w}-${r.l}-${r.s}      ${(r.dayR>=0?"+":"")}${r.dayR.toFixed(2)}R   (cum ${cum>=0?"+":""}${cum.toFixed(2)})`);
}
console.log("─".repeat(45));
console.log(`${rows.length} trading days with trades`);

// Expected US market trading days Jun 11–Jun 19 (Jun 19 = Juneteenth holiday)
const expected = ["2026-06-11","2026-06-12","2026-06-15","2026-06-16","2026-06-17","2026-06-18"];
const got = new Set(rows.map(r => r.date));
const missing = expected.filter(d => !got.has(d));
console.log(`\nExpected trading days (Jun 11–18, excl. Juneteenth 6/19): ${expected.length}`);
console.log(missing.length ? `MISSING (engine didn't trade): ${missing.join(", ")}` : "No gaps — engine traded every expected day.");

console.log("\nTRADE-BY-TRADE (clean vacation days, Jun 15+):");
console.log("DATE        TICK  DIR    ENTRY    STOP     EXIT     TYPE     R");
const detail = db.prepare(`
  SELECT date, ticker, direction, entry_price, stop_price, exit_price, exit_type, r_multiple, slippage_r
  FROM signals WHERE timeframe=5 AND was_selected=1 AND date>='2026-06-15'
  ORDER BY date, signal_time
`).all() as any[];
for (const t of detail) {
  const dirOK = "?"; // can't recompute candle here, but stop side vs entry sanity:
  const stopSane = t.direction === "LONG" ? t.stop_price < t.entry_price : t.stop_price > t.entry_price;
  console.log(
    `${t.date}  ${t.ticker.padEnd(5)} ${t.direction.padEnd(5)} ` +
    `${t.entry_price.toFixed(2).padStart(8)} ${t.stop_price.toFixed(2).padStart(8)} ${(t.exit_price??0).toFixed(2).padStart(8)}  ` +
    `${(t.exit_type||"").padEnd(7)} ${(t.r_multiple>=0?"+":"")}${(t.r_multiple??0).toFixed(2)}` +
    `${stopSane ? "" : "  <-- STOP ON WRONG SIDE"}`
  );
}
