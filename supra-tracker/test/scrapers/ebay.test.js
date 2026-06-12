const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { parseSearchHtml } = require('../../src/scrapers/ebay');

test('parses ebay search results (synthetic fixture - see file header)', () => {
  const html = fs.readFileSync(path.join(__dirname, '../fixtures/ebay-supra-synthetic.html'), 'utf8');
  const out = parseSearchHtml(html);
  assert.equal(out.length, 2); // dummy "Shop on eBay" item skipped
  const c = out[0];
  assert.equal(c.source, 'ebay');
  assert.equal(c.sourceListingId, '256401234567');
  assert.equal(c.url, 'https://www.ebay.com/itm/256401234567');
  assert.equal(c.price, 24500);
  assert.equal(c.city, 'Tempe');
  assert.equal(c.state, 'AZ');
  assert.equal(c.isAuction, true);
  assert.match(c.snippet, /7M-GTE/);
  const d = out[1];
  assert.equal(d.state, 'NV');
  assert.equal(d.isAuction, false);
});
