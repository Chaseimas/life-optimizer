const { evaluateCandidate, classifyTurbo } = require('./match');
const { distanceFromHome, geocode } = require('./geo');

// Site JSON is sloppy; coerce to bindable types so one odd field never kills a scan.
const str = (v) => (typeof v === 'string' && v ? v : typeof v === 'number' ? String(v) : null);
const num = (v) => {
  const n = typeof v === 'string' ? parseFloat(v.replace(/[^0-9.\-]/g, '')) : v;
  return typeof n === 'number' && isFinite(n) ? Math.round(n) : null;
};

// makeStore(db) so tests can inject :memory:; server uses getDb().
function makeStore(db) {
  const insL = db.prepare(`INSERT INTO listings
    (source, source_listing_id, url, title, year, price, city, state, region,
     lat, lon, distance_mi, photo_url, snippet, description, turbo_status, is_auction,
     first_seen, last_seen)
    VALUES (@source, @sourceListingId, @url, @title, @year, @price, @city, @state, @region,
     @lat, @lon, @distanceMi, @photoUrl, @snippet, @description, @turboStatus, @isAuction,
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
      for (const raw of candidates) {
        const c = {
          ...raw,
          sourceListingId: str(raw.sourceListingId),
          url: str(raw.url),
          title: str(raw.title) || '',
          price: num(raw.price),
          city: str(raw.city),
          state: str(raw.state),
          region: str(raw.region),
          photoUrl: str(raw.photoUrl),
          snippet: str(raw.snippet) || '',
          description: str(raw.description),
        };
        if (!c.sourceListingId || !c.url) { stats.rejected++; continue; }
        const ev = evaluateCandidate(c);
        if (!ev.accept) { stats.rejected++; continue; }
        seenIds.add(c.sourceListingId);
        const existing = getL.get(source, c.sourceListingId);
        if (!existing) {
          const pos = geocode(c.city, c.state);
          insL.run({
            source, sourceListingId: c.sourceListingId, url: c.url,
            title: c.title, year: ev.year, price: c.price,
            city: c.city, state: c.state, region: c.region,
            lat: pos ? pos.lat : null, lon: pos ? pos.lon : null,
            distanceMi: distanceFromHome(c.city, c.state),
            photoUrl: c.photoUrl, snippet: c.snippet, description: c.description,
            turboStatus: ev.turboStatus, isAuction: c.isAuction ? 1 : 0, now,
          });
          const row = getL.get(source, c.sourceListingId);
          insPrice.run(row.id, c.price, now);
          stats.added++;
        } else {
          if (c.price !== existing.price) {
            insPrice.run(existing.id, c.price, now);
            stats.priceChanges++;
          }
          updSeen.run({
            now, id: existing.id, title: c.title, price: c.price,
            photoUrl: c.photoUrl, turboStatus: ev.turboStatus, year: ev.year,
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
    setDescription: (id, desc) => {
      const text = String(desc ?? '');
      db.prepare('UPDATE listings SET description=? WHERE id=?').run(text, id);
      if (text) {
        const row = db.prepare('SELECT title FROM listings WHERE id=?').get(id);
        if (row) db.prepare('UPDATE listings SET turbo_status=? WHERE id=?')
          .run(classifyTurbo(`${row.title} ${text}`), id);
      }
    },
    listNeedingDescription: (limit) => db.prepare(`
      SELECT id, source, url, title FROM listings
      WHERE description IS NULL AND source IN ('craigslist','offerup') AND status='active'
      ORDER BY first_seen DESC LIMIT ?`).all(limit),
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
