const test = require('node:test');
const assert = require('node:assert');
const { createDb } = require('../src/db');

test('schema: inserts and unique constraint work', () => {
  const db = createDb(':memory:');
  const ins = db.prepare(`INSERT INTO listings
    (source, source_listing_id, url, title, first_seen, last_seen)
    VALUES (?, ?, ?, ?, ?, ?)`);
  ins.run('craigslist', '123', 'https://x', '1991 Supra', 1, 1);
  assert.throws(() => ins.run('craigslist', '123', 'https://x', 'dupe', 1, 1));
  ins.run('ebay', '123', 'https://y', 'same id, other source ok', 1, 1);
  const n = db.prepare('SELECT COUNT(*) c FROM listings').get().c;
  assert.equal(n, 2);
});
