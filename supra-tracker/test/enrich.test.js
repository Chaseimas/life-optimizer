const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { parseClBody, parseOfferUpBody } = require('../src/enrich');

const fix = (f) => fs.readFileSync(path.join(__dirname, 'fixtures', f), 'utf8');

test('parses craigslist #postingbody text', () => {
  const text = parseClBody(fix('cl-detail.html'));
  assert.ok(text && text.length > 30, `got: ${text && text.slice(0, 80)}`);
  assert.ok(!text.includes('QR Code Link to This Post'));
});

test('parses offerup detail description', () => {
  const text = parseOfferUpBody(fix('offerup-detail.html'));
  assert.ok(text && text.length > 10, `got: ${text && text.slice(0, 80)}`);
});

test('parsers return null on junk html', () => {
  assert.equal(parseClBody('<html><body>nope</body></html>'), null);
  assert.equal(parseOfferUpBody('<html><body>nope</body></html>'), null);
});
