const { SOURCES } = require('./scrapers');

// Breaker: after 3+ consecutive failures, required gap = cadence * 2^(fails-2), capped 24h.
function shouldSkip(entry, store, now = Date.now()) {
  if (store.getMeta(`demoted:${entry.source}`) === '1') return true;
  const fails = store.consecutiveFailures(entry.source);
  if (fails < 3) return false;
  const last = store.lastScans().find((s) => s.source === entry.source);
  if (!last) return false;
  const gapMs = Math.min(entry.cadenceMin * 60e3 * 2 ** (fails - 2), 24 * 3600e3);
  return now - last.started_at < gapMs;
}

async function runEntry(entry, store) {
  const startedAt = Date.now();
  try {
    const { candidates, coveredRegions } = await entry.run();
    const stats = store.ingestScan(entry.source, candidates, coveredRegions ?? null);
    store.logScan({ source: entry.source, startedAt, finishedAt: Date.now(), ok: true,
      found: candidates.length, error: null });
    store.setMeta(`blockedCount:${entry.source}`, '0');
    console.log(`[scan] ${entry.key}: ${candidates.length} found, +${stats.added} new, ${stats.priceChanges} price changes, ${stats.rejected} rejected`);
    return stats;
  } catch (e) {
    store.logScan({ source: entry.source, startedAt, finishedAt: Date.now(), ok: false,
      found: 0, error: e.message });
    console.warn(`[scan] ${entry.key} FAILED: ${e.message}`);
    if (e.blocked && entry.demotable) {
      const k = `blockedCount:${entry.source}`;
      const n = parseInt(store.getMeta(k) || '0', 10) + 1;
      store.setMeta(k, n);
      if (n >= 5) {
        store.setMeta(`demoted:${entry.source}`, '1');
        console.warn(`[scan] ${entry.key} demoted to manual-link tier after ${n} blocks`);
      }
    }
    return null;
  }
}

function start(store) {
  SOURCES.forEach((entry, i) => {
    const kickoff = i * 45e3; // stagger first runs 45s apart
    setTimeout(() => {
      const tick = () => { if (!shouldSkip(entry, store)) runEntry(entry, store); };
      tick();
      setInterval(tick, entry.cadenceMin * 60e3);
    }, kickoff);
  });
  console.log(`[scheduler] ${SOURCES.length} sources scheduled`);
}

module.exports = { start, runEntry, shouldSkip };
