// Run one scan of one source (or all) right now, then exit. Usage:
//   npm run scan                  -> all sources once
//   npm run scan -- ebay          -> just the 'ebay' entry
//   npm run scan -- craigslist-sw
const { getDb } = require('../src/db');
const { makeStore } = require('../src/store');
const { loadGeo } = require('../src/geo');
const { SOURCES } = require('../src/scrapers');
const { runEntry } = require('../src/scheduler');
const { enrichBatch } = require('../src/enrich');

(async () => {
  loadGeo();
  const store = makeStore(getDb());
  const filter = process.argv[2];
  const entries = filter ? SOURCES.filter((s) => s.key === filter) : SOURCES;
  if (entries.length === 0) {
    console.error(`no source entry named "${filter}". Options: ${SOURCES.map((s) => s.key).join(', ')}`);
    process.exit(1);
  }
  for (const e of entries) await runEntry(e, store);
  const enriched = await enrichBatch(store, 25);
  if (enriched) console.log(`enriched ${enriched} listings with full ad text`);
  const all = store.allListings();
  console.log(`done. ${all.length} total listings in db (${all.filter((l) => l.status === 'active').length} active).`);
})();
