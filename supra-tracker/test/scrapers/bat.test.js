const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { parseModelPage } = require('../../src/scrapers/bat');

test('parses BaT model page live listing cards', () => {
  const html = fs.readFileSync(path.join(__dirname, '../fixtures/bat-supra.html'), 'utf8');
  const out = parseModelPage(html);
  assert.ok(out.length >= 1, `expected at least the featured live card, got ${out.length}`);
  for (const c of out) {
    assert.equal(c.source, 'bat');
    assert.match(c.url, /bringatrailer\.com\/listing\//);
    assert.equal(c.isAuction, true);
    assert.ok(c.title.length > 3);
    assert.ok(c.sourceListingId);
  }
  // the Knockout template card (data-bind, no real href) must not leak through
  assert.ok(out.every((c) => !c.url.includes('data-bind')));
});
