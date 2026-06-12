const { evaluateCandidate } = require('./match');
const { distanceFromHome, geocode } = require('./geo');

// makeStore(db) so tests can inject :memory:; server uses getDb().
function makeStore(db) {
  const insL = db.prepare(`INSERT INTO listings
    (source, source_listing_id, url, title, year, price, city, state, region,
     lat, lon, distance_mi, photo_url, snippet, turbo_status, is_auction,
     first_seen, last_seen)
    VALUES (@source, @sourceListingId, @url, @title, @year, @price, @city, @state, @region,
     @lat, @lon, @distanceMi, @photoUrl, @snippet, @turboStatus, @isAuction,
     @now, @now)`);
  const getL = db.prepare('SELECT * FROM listings WHERE source = ? AND source_listing_id = ?');
  const updSeen = db.prepare(`UPDATE listings SET last_seen=@now, miss_count=0, status='active',
     title=@title, price=@price, photo_url=COALESCE(@photoUrl, photo_url),
     turbo_status=@turboStatus, year=COALESCE(@year, year) WHERE id=@id`);
  const insPrice = db.prepare('INSERT INTO price_history (listing_id, price, seen_at) VALUES (?, ?, ?)');

  function ingestScan(source, candidates, coveredRegions /* array or null = all */) {
    const now = Date.now();
    const stats = { added: 0, updated: 0, priceChanges: 0, rejected: 0 };
    const seenIds = new Set();

    const tx = db.transaction(() => {
      for (const c of candidates) {
        const ev = evaluateCandidate(c);
        if (!ev.accept) { stats.rejected++; continue; }
        seenIds.add(String(c.sourceListingId));
        const existing = getL.get(source, String(c.sourceListingId));
        if (!existing) {
          const pos = geocode(c.city, c.state);
          insL.run({
            source, sourceListingId: String(c.sourceListingId), url: c.url,
            title: c.title, year: ev.year, price: c.price ?? null,
            city: c.city || null, state: c.state || null, region: c.region || null,
            lat: pos ? pos.lat : null, lon: pos ? pos.lon : null,
            distanceMi: distanceFromHome(c.city, c.state),
            photoUrl: c.photoUrl || null, snippet: c.snippet || '',
            turboStatus: ev.turboStatus, isAuction: c.isAuction ? 1 : 0, now,
          });
          const row = getL.get(source, String(c.sourceListingId));
          insPrice.run(row.id, c.price ?? null, now);
          stats.added++;
        } else {
          if ((c.price ?? null) !== existing.price) {
            insPrice.run(existing.id, c.price ?? null, now);
            stats.priceChanges++;
          }
          updSeen.run({
            now, id: existing.id, title: c.title, price: c.price ?? null,
            photoUrl: c.photoUrl || null, turboStatus: ev.turboStatus, year: ev.year,
          });
          stats.updated++;
        }
      }

      // Gone detection: only listings this scan was responsible for seeing.
      const candidatesActive = coveredRegions
        ? db.prepare(`SELECT id, source_listing_id, miss_count FROM listings
                      WHERE source=? AND status='active' AND region IN (${coveredRegions.map(() => '?').join(',')})`)
            .all(source, ...coveredRegions)
        : db.prepare(`SELECT id, source_listing_id, miss_count FROM listings
                      WHERE source=? AND status='active'`).all(source);
      const bumpMiss = db.prepare('UPDATE listings SET miss_count=? WHERE id=?');
      const markGone = db.prepare(`UPDATE listings SET status='gone', miss_count=? WHERE id=?`);
      for (const row of candidatesActive) {
        if (seenIds.has(row.source_listing_id)) continue;
        const m = row.miss_count + 1;
        if (m >= 2) markGone.run(m, row.id);
        else bumpMiss.run(m, row.id);
      }
    });
    tx();
    return stats;
  }

  return {
    ingestScan,
    allListings: () => db.prepare('SELECT * FROM listings').all(),
    priceHistory: (id) => db.prepare('SELECT * FROM price_history WHERE listing_id=? ORDER BY seen_at').all(id),
    setFlag: (id, field, val) => {
      if (!['favorite', 'hidden'].includes(field)) throw new Error('bad flag');
      db.prepare(`UPDATE listings SET ${field}=? WHERE id=?`).run(val ? 1 : 0, id);
    },
    getMeta: (k) => { const r = db.prepare('SELECT value FROM meta WHERE key=?').get(k); return r ? r.value : null; },
    setMeta: (k, v) => db.prepare('INSERT INTO meta (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value').run(k, String(v)),
    logScan: ({ source, startedAt, finishedAt, ok, found, error }) =>
      db.prepare(`INSERT INTO scan_log (source, started_at, finished_at, ok, listings_found, error_text)
                  VALUES (?,?,?,?,?,?)`).run(source, startedAt, finishedAt, ok ? 1 : 0, found, error),
    consecutiveFailures: (source) => {
      const rows = db.prepare('SELECT ok FROM scan_log WHERE source=? ORDER BY started_at DESC LIMIT 10').all(source);
      let n = 0;
      for (const r of rows) { if (r.ok) break; n++; }
      return n;
    },
    lastScans: () => db.prepare(`
      SELECT s.source, s.started_at, s.finished_at, s.ok, s.listings_found, s.error_text
      FROM scan_log s
      JOIN (SELECT source, MAX(started_at) m FROM scan_log GROUP BY source) latest
        ON latest.source = s.source AND latest.m = s.started_at`).all(),
    lastOkScans: () => db.prepare(`
      SELECT source, MAX(started_at) last_ok FROM scan_log WHERE ok=1 GROUP BY source`).all(),
    queryListings: () => db.prepare(`
      SELECT l.*, (SELECT ph.price FROM price_history ph WHERE ph.listing_id = l.id
                   ORDER BY ph.seen_at DESC LIMIT 1 OFFSET 1) AS prev_price
      FROM listings l ORDER BY first_seen DESC`).all(),
  };
}

module.exports = { makeStore };
