// Dev tool: list active CL/OfferUp listing URLs (for capturing detail fixtures).
const { getDb } = require('../src/db');

const rows = getDb().prepare(
  "SELECT source, url FROM listings WHERE source IN ('craigslist','offerup') AND status='active'"
).all();
for (const r of rows) console.log(`${r.source} ${r.url}`);
