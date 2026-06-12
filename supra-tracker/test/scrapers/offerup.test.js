const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { parseNextData } = require('../../src/scrapers/offerup');

test('parses offerup __NEXT_DATA__ listings (live fixture)', () => {
  const html = fs.readFileSync(path.join(__dirname, '../fixtures/offerup-supra.html'), 'utf8');
  const out = parseNextData(html);
  assert.ok(out.length >= 5, `expected several items, got ${out.length}`);
  for (const c of out) {
    assert.equal(c.source, 'offerup');
    assert.ok(c.sourceListingId);
    assert.match(c.url, /^https:\/\/offerup\.com\//);
    assert.ok(c.title.length > 3);
  }
  assert.ok(out.some((c) => c.city && c.state === 'AZ'), 'expected AZ locations');
  assert.ok(out.some((c) => typeof c.price === 'number'));
  // image field is an object in their JSON - we must extract the string url
  assert.ok(out.some((c) => typeof c.photoUrl === 'string' && c.photoUrl.startsWith('https://')));
});
