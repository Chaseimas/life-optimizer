import { getDb } from "../index";
import type { Outcome, ExitType } from "../../types";

export function insertSignal(signal: {
  ticker: string;
  date: string;
  timeframe: number;
  direction: string;
  grade: string;
  range_high: number;
  range_low: number;
  range_width: number;
  entry_price: number;
  stop_price: number;
  target_price: number;
  risk: number;
  signal_time: string;
  vwap_at_entry: number;
  breakout_volume_ratio: number;
  breakout_candle_quality: number;
  ranking_score: number;
  was_selected: number;
  range_atr_pct: number;
  gap_pct: number;
  gap_aligned: number;
  trend_aligned: number;
  sma_slope: number;
}): number {
  const db = getDb();
  const stmt = db.prepare(`
    INSERT INTO signals (
      ticker, date, timeframe, direction, grade,
      range_high, range_low, range_width,
      entry_price, stop_price, target_price, risk,
      signal_time, vwap_at_entry, breakout_volume_ratio, breakout_candle_quality,
      ranking_score, was_selected,
      range_atr_pct, gap_pct, gap_aligned, trend_aligned, sma_slope
    ) VALUES (
      @ticker, @date, @timeframe, @direction, @grade,
      @range_high, @range_low, @range_width,
      @entry_price, @stop_price, @target_price, @risk,
      @signal_time, @vwap_at_entry, @breakout_volume_ratio, @breakout_candle_quality,
      @ranking_score, @was_selected,
      @range_atr_pct, @gap_pct, @gap_aligned, @trend_aligned, @sma_slope
    )
  `);
  const result = stmt.run(signal);
  return Number(result.lastInsertRowid);
}

export function updateSignalOutcome(id: number, update: {
  outcome: Outcome;
  exit_type: ExitType;
  exit_price: number;
  exit_time: string;
  r_multiple: number;
  target_hit: number;
  max_favorable: number;
  max_adverse: number;
}): void {
  const db = getDb();
  db.prepare(`
    UPDATE signals SET
      outcome = @outcome, exit_type = @exit_type,
      exit_price = @exit_price, exit_time = @exit_time,
      r_multiple = @r_multiple, target_hit = @target_hit,
      max_favorable = @max_favorable, max_adverse = @max_adverse
    WHERE id = @id
  `).run({ id, ...update });
}

export function getSignalsByDate(date: string) {
  return getDb().prepare("SELECT * FROM signals WHERE date = ? ORDER BY ranking_score DESC").all(date);
}

export function getSignalHistory(limit = 100, offset = 0) {
  return getDb().prepare(
    "SELECT * FROM signals WHERE was_selected = 1 ORDER BY date DESC, signal_time DESC LIMIT ? OFFSET ?"
  ).all(limit, offset);
}

export function getPerformanceStats() {
  const db = getDb();
  return db.prepare(`
    SELECT
      COUNT(*) as total,
      SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
      SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
      SUM(CASE WHEN outcome = 'SCRATCH' THEN 1 ELSE 0 END) as scratches,
      COALESCE(SUM(r_multiple), 0) as total_r,
      AVG(r_multiple) as avg_r,
      AVG(CASE WHEN outcome = 'WIN' THEN r_multiple END) as avg_win_r,
      AVG(CASE WHEN outcome = 'LOSS' THEN r_multiple END) as avg_loss_r,
      CASE WHEN SUM(CASE WHEN r_multiple < 0 THEN ABS(r_multiple) ELSE 0 END) > 0
        THEN SUM(CASE WHEN r_multiple > 0 THEN r_multiple ELSE 0 END) /
             SUM(CASE WHEN r_multiple < 0 THEN ABS(r_multiple) ELSE 0 END)
        ELSE 0 END as profit_factor
    FROM signals WHERE was_selected = 1 AND outcome IS NOT NULL
  `).get();
}
