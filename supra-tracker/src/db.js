const Database = require('better-sqlite3');
const fs = require('fs');
const path = require('path');
const config = require('./config');

const SCHEMA = `
CREATE TABLE IF NOT EXISTS listings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  source_listing_id TEXT NOT NULL,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  year INTEGER,
  price INTEGER,
  city TEXT,
  state TEXT,
  region TEXT,
  lat REAL,
  lon REAL,
  distance_mi REAL,
  photo_url TEXT,
  snippet TEXT DEFAULT '',
  turbo_status TEXT DEFAULT 'unconfirmed',
  is_auction INTEGER DEFAULT 0,
  first_seen INTEGER NOT NULL,
  last_seen INTEGER NOT NULL,
  miss_count INTEGER DEFAULT 0,
  status TEXT DEFAULT 'active',
  favorite INTEGER DEFAULT 0,
  hidden INTEGER DEFAULT 0,
  UNIQUE(source, source_listing_id)
);
CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status);
CREATE INDEX IF NOT EXISTS idx_listings_source ON listings(source);

CREATE TABLE IF NOT EXISTS price_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listing_id INTEGER NOT NULL REFERENCES listings(id),
  price INTEGER,
  seen_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_listing ON price_history(listing_id);

CREATE TABLE IF NOT EXISTS scan_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  started_at INTEGER NOT NULL,
  finished_at INTEGER,
  ok INTEGER DEFAULT 0,
  listings_found INTEGER DEFAULT 0,
  error_text TEXT
);
CREATE INDEX IF NOT EXISTS idx_scanlog_source ON scan_log(source, started_at);

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT
);
`;

function createDb(file) {
  if (file !== ':memory:') fs.mkdirSync(path.dirname(file), { recursive: true });
  const db = new Database(file);
  db.pragma('journal_mode = WAL');
  db.exec(SCHEMA);
  // Migrations for dbs created before these columns existed (no-op when present)
  try { db.exec('ALTER TABLE listings ADD COLUMN description TEXT'); } catch { /* exists */ }
  return db;
}

let _db = null;
function getDb() {
  if (!_db) _db = createDb(path.join(config.DATA_DIR, 'supra.db'));
  return _db;
}

module.exports = { createDb, getDb };
