const test = require('node:test');
const assert = require('node:assert');
const { createDb } = require('../src/db');
const { makeStore } = require('../src/store');
const { makeApp } = require('../src/api');

function seed(store) {
  store.ingestScan('craigslist', [{
    source: 'craigslist', sourceListingId: '1', url: 'https://cl/1',
    title: '1991 Toyota Supra Turbo', price: 14000, city: 'Mesa', state: 'AZ',
    region: 'phoenix', photoUrl: null, snippet: '', year: null, isAuction: false,
  }], ['phoenix']);
}

test('GET /api/listings returns listings, sources, newSince; flag round-trips', async () => {
  const store = makeStore(createDb(':memory:'));
  seed(store);
  const app = makeApp(store);
  const srv = app.listen(0);
  const base = `http://127.0.0.1:${srv.address().port}`;
  const r1 = await fetch(`${base}/api/listings`);
  assert.equal(r1.status, 200);
  const body = await r1.json();
  assert.equal(body.listings.length, 1);
  assert.equal(body.listings[0].turbo_status, 'confirmed');
  assert.ok(Array.isArray(body.sources));
  assert.ok('newSince' in body);
  assert.ok(body.home.label.includes('Mesa'));
  assert.ok(body.tier2.length >= 5);

  // favorite + hide round-trip
  const id = body.listings[0].id;
  const rf = await fetch(`${base}/api/listings/${id}/flag`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ field: 'favorite', value: true }),
  });
  assert.equal(rf.status, 200);
  const r2 = await (await fetch(`${base}/api/listings`)).json();
  assert.equal(r2.listings[0].favorite, 1);

  // tier2 checked timestamp
  await fetch(`${base}/api/tier2/fb-phoenix/checked`, { method: 'POST' });
  const r3 = await (await fetch(`${base}/api/listings`)).json();
  assert.ok(r3.tier2.find((t) => t.key === 'fb-phoenix').lastChecked > 0);

  // bad flag field rejected
  const rb = await fetch(`${base}/api/listings/${id}/flag`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ field: 'status', value: 'gone' }),
  });
  assert.equal(rb.status, 400);
  srv.close();
});

test('listings carry donor fields; /api/plan returns 9 phases', async () => {
  const store = makeStore(createDb(':memory:'));
  seed(store);
  const app = makeApp(store);
  const srv = app.listen(0);
  const base = `http://127.0.0.1:${srv.address().port}`;
  const body = await (await fetch(`${base}/api/listings`)).json();
  const l = body.listings[0];
  assert.ok(typeof l.donor_score === 'number');
  assert.ok(['great', 'possible', 'poor'].includes(l.donor_tier));
  assert.ok(Array.isArray(l.donor_reasons) && l.donor_reasons.length > 0);

  const plan = await (await fetch(`${base}/api/plan`)).json();
  assert.equal(plan.phases.length, 9);
  assert.ok(plan.phases[0].name.toLowerCase().includes('buy'));
  assert.equal(plan.finals.length, 3);
  srv.close();
});
