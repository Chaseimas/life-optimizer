const test = require('node:test');
const assert = require('node:assert');
const { createDb } = require('../src/db');
const { makeStore } = require('../src/store');
const { runEntry, shouldSkip } = require('../src/scheduler');

test('runEntry: success ingests and logs ok', async () => {
  const store = makeStore(createDb(':memory:'));
  const entry = {
    key: 'fake', source: 'ebay', label: 'Fake', cadenceMin: 60,
    run: async () => ({
      candidates: [{ source: 'ebay', sourceListingId: '1', url: 'https://e/1',
        title: '1991 Toyota Supra Turbo', price: 9000, city: null, state: null,
        region: null, photoUrl: null, snippet: '', year: null, isAuction: false }],
      coveredRegions: null,
    }),
  };
  await runEntry(entry, store);
  assert.equal(store.allListings().length, 1);
  assert.equal(store.consecutiveFailures('ebay'), 0);
});

test('runEntry: failure logs error, never throws', async () => {
  const store = makeStore(createDb(':memory:'));
  const entry = { key: 'bad', source: 'bat', label: 'Bad', cadenceMin: 60,
    run: async () => { throw new Error('HTTP 503'); } };
  await runEntry(entry, store);
  assert.equal(store.consecutiveFailures('bat'), 1);
});

test('shouldSkip: breaker backs off after 3 consecutive failures', () => {
  const store = makeStore(createDb(':memory:'));
  const now = Date.now();
  for (let i = 0; i < 3; i++) {
    store.logScan({ source: 'bat', startedAt: now - 1000 + i, finishedAt: now - 999 + i, ok: false, found: 0, error: 'x' });
  }
  const entry = { key: 'bat', source: 'bat', cadenceMin: 60 };
  assert.equal(shouldSkip(entry, store, now), true);            // just failed 3x -> back off
  assert.equal(shouldSkip(entry, store, now + 5 * 3600e3), false); // long after backoff window
});

test('demotion: 5 consecutive blocked errors set demoted meta', async () => {
  const store = makeStore(createDb(':memory:'));
  const entry = { key: 'offerup', source: 'offerup', label: 'OfferUp', cadenceMin: 60, demotable: true,
    run: async () => { const e = new Error('blocked'); e.blocked = true; throw e; } };
  for (let i = 0; i < 5; i++) await runEntry(entry, store);
  assert.equal(store.getMeta('demoted:offerup'), '1');
  // and shouldSkip respects demotion permanently
  assert.equal(shouldSkip(entry, store), true);
});
