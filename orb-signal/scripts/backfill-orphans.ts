/**
 * One-off backfill: the 2026-06-11 orphan trades (TSLA, AMD) that filled after the
 * engine abandoned them. Fills recovered from Alpaca order history. R computed
 * against the intended $1,000 (1%) risk sizing. Range fields are reconstructions.
 */
import { insertSignal, updateSignalOutcome } from "../src/lib/db/queries/signals";

const ORPHANS = [
  {
    ticker: "TSLA", direction: "SHORT", qty: 136,
    entry: 381.471324, exit: 388.11,
    entryTime: "2026-06-11T13:38:16Z", exitTime: "2026-06-11T13:56:00Z",
  },
  {
    ticker: "AMD", direction: "LONG", qty: 157,
    entry: 467.885223, exit: 461.656242,
    entryTime: "2026-06-11T13:38:13Z", exitTime: "2026-06-11T15:01:32Z",
  },
];

for (const o of ORPHANS) {
  const pnlPerShare = o.direction === "LONG" ? o.exit - o.entry : o.entry - o.exit;
  const pnlDollars = pnlPerShare * o.qty;
  const rMultiple = pnlDollars / 1000; // intended 1% risk on $100k
  const riskPerShare = Math.abs(o.entry - o.exit);

  const id = insertSignal({
    ticker: o.ticker, date: "2026-06-11", timeframe: 5,
    direction: o.direction, grade: "A",
    range_high: o.direction === "SHORT" ? o.exit : o.entry,
    range_low: o.direction === "SHORT" ? o.entry : o.exit,
    range_width: riskPerShare,
    entry_price: o.entry, stop_price: o.exit, target_price: o.entry,
    risk: riskPerShare,
    signal_time: o.entryTime,
    vwap_at_entry: 0, breakout_volume_ratio: 0, breakout_candle_quality: 0,
    ranking_score: 0, was_selected: 1,
    range_atr_pct: 0, gap_pct: 0, gap_aligned: 0, trend_aligned: 1, sma_slope: 0,
    slippage_r: null,
  });
  updateSignalOutcome(id, {
    outcome: "LOSS", exit_type: "stop",
    exit_price: o.exit, exit_time: o.exitTime,
    r_multiple: rMultiple, target_hit: 0,
    max_favorable: o.entry, max_adverse: o.exit,
  });
  console.log(`backfilled ${o.ticker} ${o.direction}: ${rMultiple.toFixed(2)}R ($${pnlDollars.toFixed(0)})`);
}
