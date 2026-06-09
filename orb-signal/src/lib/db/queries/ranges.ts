import { getDb } from "../index";

export function insertRange(range: {
  ticker: string;
  date: string;
  timeframe: number;
  range_high: number;
  range_low: number;
  range_width: number;
  open_price: number;
  close_price: number;
  volume: number;
  vwap_at_close: number;
  atr_14: number;
  sma_20: number;
  sma_slope: number;
  prior_day_high: number;
  prior_day_low: number;
  prior_day_close: number;
  premarket_price: number;
  gap_pct: number;
  gap_direction: string;
  quality_grade: string;
  skip_reason: string | null;
}): number {
  const db = getDb();
  const result = db.prepare(`
    INSERT OR REPLACE INTO opening_ranges (
      ticker, date, timeframe, range_high, range_low, range_width,
      open_price, close_price, volume, vwap_at_close,
      atr_14, sma_20, sma_slope,
      prior_day_high, prior_day_low, prior_day_close, premarket_price,
      gap_pct, gap_direction, quality_grade, skip_reason
    ) VALUES (
      @ticker, @date, @timeframe, @range_high, @range_low, @range_width,
      @open_price, @close_price, @volume, @vwap_at_close,
      @atr_14, @sma_20, @sma_slope,
      @prior_day_high, @prior_day_low, @prior_day_close, @premarket_price,
      @gap_pct, @gap_direction, @quality_grade, @skip_reason
    )
  `).run(range);
  return Number(result.lastInsertRowid);
}

export function getRangesByDate(date: string) {
  return getDb().prepare("SELECT * FROM opening_ranges WHERE date = ? ORDER BY ticker, timeframe").all(date);
}
