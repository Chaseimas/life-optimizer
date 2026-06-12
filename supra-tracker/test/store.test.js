const test = require('node:test');
const assert = require('node:assert');
const { createDb } = require('../src/db');
const { makeStore } = require('../src/store');

const cand = (over = {}) => ({
  source: 'craigslist', sourceListingId: 'a1', url: 'https://x/1',
  title: '1991 Toyota Supra Turbo', price: 12000, city: 'Mesa', state: 'AZ',
  region: 'phoenix', photoUrl: null, snippet: '', year: null, isAuction: false,
  ...over,
});

test('ingest: new listing inserted with match fields + price history row', () => {
  const store = makeStore(createDb(':memory:'));
  const stats = store.ingestScan('craigslist', [cand()], ['phoenix']);
  assert.equal(stats.added, 1);
  const l = store.allListings()[0];
  assert.equal(l.year, 1991);
  assert.equal(l.turbo_status, 'confirmed');
  assert.equal(l.status, 'active');
  assert.equal(store.priceHistory(l.id).length, 1);
});

test('ingest: rejects MK4 and non-matching', () => {
  const store = makeStore(createDb(':memory:'));
  const stats = store.ingestScan('craigslist', [cand({ title: '1994 Toyota Supra', sourceListingId: 'mk4' })], ['phoenix']);
  assert.equal(stats.added, 0);
});

test('price change appends history and updates listing', () => {
  const store = makeStore(createDb(':memory:'));
  store.ingestScan('craigslist', [cand()], ['phoenix']);
  store.ingestScan('craigslist', [cand({ price: 10500 })], ['phoenix']);
  const l = store.allListings()[0];
  assert.equal(l.price, 10500);
  assert.equal(store.priceHistory(l.id).length, 2);
});

test('gone detection: 2 consecutive misses within covered regions only', () => {
  const store = makeStore(createDb(':memory:'));
  store.ingestScan('craigslist', [cand()], ['phoenix']);
  // scan that covers a DIFFERENT region must not count as a miss
  store.ingestScan('craigslist', [cand({ sourceListingId: 'other', region: 'tucson', city: 'Tucson' })], ['tucson']);
  assert.equal(store.allListings().find((l) => l.source_listing_id === 'a1').status, 'active');
  // two covering scans without the listing -> gone
  store.ingestScan('craigslist', [], ['phoenix']);
  assert.equal(store.allListings().find((l) => l.source_listing_id === 'a1').status, 'active'); // miss 1
  store.ingestScan('craigslist', [], ['phoenix']);
  assert.equal(store.allListings().find((l) => l.source_listing_id === 'a1').status, 'gone');  // miss 2
  // reappearing revives it
  store.ingestScan('craigslist', [cand()], ['phoenix']);
  assert.equal(store.allListings().find((l) => l.source_listing_id === 'a1').status, 'active');
});

test('ingest survives non-string field types from sloppy site JSON', () => {
  const store = makeStore(createDb(':memory:'));
  const stats = store.ingestScan('offerup', [cand({
    source: 'offerup',
    sourceListingId: 12345,                       // number id
    photoUrl: { url: 'https://img/x.jpg' },       // object instead of string
    price: '8500',                                // string price
    title: '1990 Toyota Supra Turbo',
  })], null);
  assert.equal(stats.added, 1);
  const l = store.allListings()[0];
  assert.equal(l.photo_url, null);                // unusable -> stored as null
  assert.equal(l.price, 8500);
});

test('ingest stores description when the scraper provides one; setDescription updates turbo', () => {
  const store = makeStore(createDb(':memory:'));
  store.ingestScan('classiccars', [cand({
    source: 'classiccars', sourceListingId: 'cc1',
    description: 'Body is rust free. This is the non turbo model.',
    title: '1988 Toyota Supra',
  })], null);
  let l = store.allListings()[0];
  assert.match(l.description, /rust free/);

  // enrichment path: description arrives later and upgrades turbo_status
  store.ingestScan('craigslist', [cand({ sourceListingId: 'cl1', title: '1990 Toyota Supra clean' })], ['phoenix']);
  l = store.allListings().find((x) => x.source_listing_id === 'cl1');
  assert.equal(l.turbo_status, 'unconfirmed');
  store.setDescription(l.id, 'Original 7M-GTE turbo runs strong, rust free underneath');
  l = store.allListings().find((x) => x.source_listing_id === 'cl1');
  assert.match(l.description, /7M-GTE/i);
  assert.equal(l.turbo_status, 'confirmed');

  // failure sentinel: empty string stored, turbo untouched
  store.setDescription(l.id, '');
  assert.equal(store.allListings().find((x) => x.source_listing_id === 'cl1').description, '');
});

test('meta get/set and scan log', () => {
  const store = makeStore(createDb(':memory:'));
  store.setMeta('k', 'v');
  assert.equal(store.getMeta('k'), 'v');
  store.logScan({ source: 'ebay', startedAt: 1, finishedAt: 2, ok: true, found: 5, error: null });
  store.logScan({ source: 'ebay', startedAt: 3, finishedAt: 4, ok: false, found: 0, error: 'HTTP 503' });
  assert.equal(store.consecutiveFailures('ebay'), 1);
  assert.equal(store.lastScans().find((s) => s.source === 'ebay').error_text, 'HTTP 503');
});
