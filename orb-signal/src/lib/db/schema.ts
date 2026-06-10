import type Database from "better-sqlite3";

export function initSchema(db: Database.Database): void {
  db.exec(`
    CREATE TABLE IF NOT EXISTS opening_ranges (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ticker TEXT NOT NULL,
      date TEXT NOT NULL,
      timeframe INTEGER NOT NULL,
      range_high REAL NOT NULL,
      range_low REAL NOT NULL,
      range_width REAL NOT NULL,
      open_price REAL NOT NULL,
      close_price REAL NOT NULL,
      volume REAL NOT NULL,
      vwap_at_close REAL NOT NULL,
      atr_14 REAL NOT NULL,
      sma_20 REAL NOT NULL,
      sma_slope REAL NOT NULL,
      prior_day_high REAL NOT NULL,
      prior_day_low REAL NOT NULL,
      prior_day_close REAL NOT NULL,
      premarket_price REAL NOT NULL,
      gap_pct REAL NOT NULL,
      gap_direction TEXT NOT NULL,
      quality_grade TEXT NOT NULL,
      skip_reason TEXT,
      UNIQUE(ticker, date, timeframe)
    );

    CREATE TABLE IF NOT EXISTS signals (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ticker TEXT NOT NULL,
      date TEXT NOT NULL,
      timeframe INTEGER NOT NULL,
      direction TEXT NOT NULL,
      grade TEXT NOT NULL,
      range_high REAL NOT NULL,
      range_low REAL NOT NULL,
      range_width REAL NOT NULL,
      entry_price REAL NOT NULL,
      stop_price REAL NOT NULL,
      target_price REAL NOT NULL,
      risk REAL NOT NULL,
      signal_time TEXT NOT NULL,
      vwap_at_entry REAL NOT NULL,
      breakout_volume_ratio REAL NOT NULL,
      breakout_candle_quality REAL NOT NULL,
      outcome TEXT,
      exit_type TEXT,
      exit_price REAL,
      exit_time TEXT,
      r_multiple REAL,
      target_hit INTEGER DEFAULT 0,
      ranking_score REAL NOT NULL,
      was_selected INTEGER DEFAULT 0,
      max_favorable REAL,
      max_adverse REAL,
      skipped INTEGER DEFAULT 0,
      skip_reason TEXT,
      range_atr_pct REAL NOT NULL,
      gap_pct REAL NOT NULL,
      gap_aligned INTEGER NOT NULL,
      trend_aligned INTEGER NOT NULL,
      sma_slope REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(date);
    CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);
    CREATE INDEX IF NOT EXISTS idx_ranges_date ON opening_ranges(date);
  `);

  // Migrations for columns added after initial release
  try { db.exec("ALTER TABLE signals ADD COLUMN slippage_r REAL"); } catch { /* exists */ }
}
