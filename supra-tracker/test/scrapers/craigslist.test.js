const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { parseSearchHtml } = require('../../src/scrapers/craigslist');

const fix = (f) => fs.readFileSync(path.join(__dirname, '../fixtures', f), 'utf8');

test('parses craigslist static search results (LA fixture has items)', () => {
  const out = parseSearchHtml(fix('craigslist-la.html'), 'losangeles', 'CA');
  assert.ok(out.length > 10, `expected many items, got ${out.length}`);
  const c = out.find((x) => /supra/i.test(x.title)) || out[0];
  assert.equal(c.source, 'craigslist');
  assert.match(String(c.sourceListingId), /^\d{8,}$/);
  assert.match(c.url, /^https:\/\/.*craigslist\.org/);
  assert.ok(c.title.length > 3);
  assert.equal(c.region, 'losangeles');
  assert.equal(c.state, 'CA');
  assert.ok(out.some((x) => typeof x.price === 'number'));
  assert.ok(out.some((x) => x.city));
});

test('empty results page parses to empty array (Phoenix fixture)', () => {
  const out = parseSearchHtml(fix('craigslist-phoenix.html'), 'phoenix', 'AZ');
  assert.deepEqual(out, []);
});
