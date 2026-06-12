const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const hemmings = require('../../src/scrapers/hemmings');
const classiccars = require('../../src/scrapers/classiccars');

const fix = (f) => fs.readFileSync(path.join(__dirname, '../fixtures', f), 'utf8');

test('classiccars parser (live fixture)', () => {
  const out = classiccars.parseSearchHtml(fix('classiccars-supra.html'));
  assert.ok(out.length >= 5, `expected several A70s, got ${out.length}`);
  for (const c of out) {
    assert.equal(c.source, 'classiccars');
    assert.match(c.url, /^https:\/\/classiccars\.com\/listings\/view\/\d+/);
    assert.match(String(c.sourceListingId), /^\d{5,}$/);
    assert.ok(c.title.length > 3);
    assert.ok(c.year >= 1986 && c.year <= 1992, `year ${c.year}`);
    assert.ok(typeof c.price === 'number');
  }
  // location parsed from URL slug, including a two-word state
  const ny = out.find((c) => c.url.includes('new-york'));
  assert.ok(ny);
  assert.equal(ny.state, 'NY');
  assert.equal(ny.city, 'binghamton');
});

test('classiccars locationFromSlug edge cases', () => {
  const f = classiccars.locationFromSlug;
  assert.deepEqual(f('/listings/view/1/1986-toyota-supra-for-sale-in-lutz-florida-33559'),
    { city: 'lutz', state: 'FL' });
  assert.deepEqual(f('/listings/view/1/1988-supra-for-sale-in-sherwood-park-alberta-t8h-0x5'),
    { city: null, state: null }); // Canada -> no US state
  assert.deepEqual(f('/listings/view/1/1990-supra-for-sale-in-galveston-texas-77550'),
    { city: 'galveston', state: 'TX' });
});

test('hemmings parser (synthetic fixture - source is CF-blocked)', () => {
  const out = hemmings.parseSearchHtml(fix('hemmings-supra-synthetic.html'));
  assert.equal(out.length, 2);
  const c = out[0];
  assert.equal(c.source, 'hemmings');
  assert.equal(c.sourceListingId, '2789912');
  assert.equal(c.price, 28500);
  assert.equal(c.city, 'Scottsdale');
  assert.equal(c.state, 'AZ');
  assert.equal(c.year, 1991);
  assert.match(out[1].url, /^https:\/\/www\.hemmings\.com\//);
});
