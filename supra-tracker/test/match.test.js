const test = require('node:test');
const assert = require('node:assert');
const { extractYear, classifyTurbo, evaluateCandidate } = require('../src/match');

test('extractYear: 4-digit years', () => {
  assert.equal(extractYear('1991 Toyota Supra Turbo'), 1991);
  assert.equal(extractYear('Toyota Supra 1987 targa'), 1987);
  assert.equal(extractYear('1994 Supra'), 1994); // out of range is the caller's problem
});

test('extractYear: apostrophe two-digit years', () => {
  assert.equal(extractYear("'91 Supra turbo"), 1991);
  assert.equal(extractYear('Supra ’89'), 1989); // curly apostrophe
});

test('extractYear: does not bite on prices or part numbers', () => {
  assert.equal(extractYear('Supra turbo $8,900 obo'), null);
  assert.equal(extractYear('Supra wheels 89mm offset'), null);
});

test('classifyTurbo: confirmed turbo keywords', () => {
  for (const t of ['Supra Turbo', '7M-GTE swap', '7mgte runs great', '1JZ swapped', 'twin turbo jdm', 'turbocharged targa']) {
    assert.equal(classifyTurbo(t), 'confirmed', t);
  }
});

test('classifyTurbo: confirmed non-turbo', () => {
  for (const t of ['non-turbo 5 speed', 'non turbo targa', 'NA supra clean', '7M-GE engine', '7mge motor']) {
    assert.equal(classifyTurbo(t), 'non_turbo', t);
  }
});

test('classifyTurbo: unconfirmed when silent or conflicting', () => {
  assert.equal(classifyTurbo('1991 Toyota Supra clean title'), 'unconfirmed');
  assert.equal(classifyTurbo('turbo... not the non-turbo'), 'unconfirmed');
  // "na" must be a standalone word - "nationwide" is not NA
  assert.equal(classifyTurbo('nationwide shipping supra'), 'unconfirmed');
});

test('evaluateCandidate: accepts in-range, rejects MK4/MK2, keeps keyword-tagged unknown year', () => {
  const base = { title: '', snippet: '', year: null };
  assert.equal(evaluateCandidate({ ...base, title: '1991 Toyota Supra Turbo' }).accept, true);
  assert.equal(evaluateCandidate({ ...base, title: '1994 Toyota Supra' }).accept, false);
  assert.equal(evaluateCandidate({ ...base, title: '1984 Toyota Supra' }).accept, false);
  // no year, but MK3 keyword => keep as year-unknown
  const r = evaluateCandidate({ ...base, title: 'Toyota Supra MK3 project' });
  assert.equal(r.accept, true);
  assert.equal(r.year, null);
  // no year, no mk3 keyword => reject
  assert.equal(evaluateCandidate({ ...base, title: 'Toyota Supra' }).accept, false);
  // structured year from site wins over text
  assert.equal(evaluateCandidate({ ...base, year: 1990, title: 'Toyota Supra' }).accept, true);
});

test('evaluateCandidate: rejects non-Supra vehicles even with in-range years', () => {
  // search engines fuzzy-match; a "toyota supra" query returns Camrys and Venzas too
  const base = { title: '', snippet: '', year: null };
  assert.equal(evaluateCandidate({ ...base, title: '1990 Toyota Camry excellent' }).accept, false);
  assert.equal(evaluateCandidate({ ...base, year: 1991, title: '2015 Toyota Venza - Cash!' }).accept, false);
  assert.equal(evaluateCandidate({ ...base, title: '1991 Celica Supra' }).accept, true);
});
