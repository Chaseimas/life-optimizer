const test = require('node:test');
const assert = require('node:assert');
const { scoreDonor } = require('../src/score');

const L = (over = {}) => ({
  title: '1989 Toyota Supra', snippet: '', description: '',
  price: 5000, state: 'OH', turbo_status: 'unconfirmed', ...over,
});

const has = (r, txt) => r.reasons.some((x) => x.text.includes(txt));

test('price bands', () => {
  assert.ok(has(scoreDonor(L({ price: 5000 })), 'in Phase-1 budget'));
  assert.ok(has(scoreDonor(L({ price: 800 })), 'suspiciously cheap'));
  assert.ok(has(scoreDonor(L({ price: 10000 })), 'slightly over'));
  assert.ok(has(scoreDonor(L({ price: 15000 })), 'over budget'));
  assert.ok(has(scoreDonor(L({ price: 46000 })), 'way over budget'));
  assert.ok(has(scoreDonor(L({ price: null })), 'no price'));
});

test('rust: positive, structural, cosmetic, generic precedence', () => {
  const pos = scoreDonor(L({ description: 'rust free arizona car, solid floors' }));
  assert.ok(has(pos, 'rust-free / solid'));
  assert.ok(!has(pos, 'rust mentioned'), 'positive must not double-count as generic');
  assert.ok(!has(pos, 'structural'), '"solid floors"+"no rot" style text must not look structural');

  const struct = scoreDonor(L({ description: 'some rust in the rocker panels' }));
  assert.ok(has(struct, 'structural rust'));
  assert.ok(!has(struct, 'rust mentioned'), 'structural suppresses generic');

  const cosm = scoreDonor(L({ description: 'minor surface rust on the hood' }));
  assert.ok(has(cosm, 'cosmetic rust'));
  assert.ok(!has(cosm, 'rust mentioned'), 'cosmetic suppresses generic');

  const gen = scoreDonor(L({ description: 'has some rust, runs great' }));
  assert.ok(has(gen, 'rust mentioned'));

  // "rotors" must not trip rust/rot rules
  const rotor = scoreDonor(L({ description: 'new brake rotors and floors carpets' }));
  assert.ok(!has(rotor, 'structural') && !has(rotor, 'rust mentioned'));
});

test('title status + condition cap', () => {
  assert.ok(has(scoreDonor(L({ description: 'clean title in hand' })), 'clean title'));
  assert.ok(has(scoreDonor(L({ description: 'salvage title' })), 'branded/missing title'));
  const kept = scoreDonor(L({ description: 'garage kept, original paint, one owner, straight body' }));
  const condDeltas = kept.reasons.filter((r) => r.text.includes('well-kept'));
  assert.equal(condDeltas.length, 1);
  assert.ok(condDeltas[0].delta <= 10);
});

test('dead-engine donor logic gated by price', () => {
  assert.ok(has(scoreDonor(L({ price: 4000, description: 'blown engine, doesnt run' })), 'donor deal'));
  assert.ok(has(scoreDonor(L({ price: 12000, description: 'needs engine' })), 'priced like a runner'));
  assert.ok(has(scoreDonor(L({ price: 8000, description: 'engine out, roller' })), 'engine condition irrelevant'));
  assert.ok(has(scoreDonor(L({ description: 'parting out, parts car' })), 'parts car'));
});

test('frame damage, dry state, non-turbo bonus', () => {
  assert.ok(has(scoreDonor(L({ description: 'frame damage from accident' })), 'frame/accident'));
  assert.ok(has(scoreDonor(L({ state: 'AZ' })), 'dry-climate'));
  assert.ok(has(scoreDonor(L({ turbo_status: 'non_turbo' })), 'non-turbo'));
});

test('score clamps 0-100 and tiers map', () => {
  const great = scoreDonor(L({ price: 5000, state: 'AZ', description: 'rust free, clean title, garage kept' }));
  assert.ok(great.score >= 70 && great.tier === 'great', `got ${great.score}`);
  const poor = scoreDonor(L({ price: 46000, description: 'rust in floor pans, salvage title, wrecked' }));
  assert.ok(poor.score < 50 && poor.tier === 'poor', `got ${poor.score}`);
  assert.ok(poor.score >= 0);
  const mid = scoreDonor(L({}));
  assert.ok(['possible', 'great', 'poor'].includes(mid.tier));
  // reasons sorted by |delta| descending
  const r = great.reasons.map((x) => Math.abs(x.delta));
  assert.deepEqual(r, [...r].sort((a, b) => b - a));
});
