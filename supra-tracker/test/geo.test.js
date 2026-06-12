const test = require('node:test');
const assert = require('node:assert');
const { haversineMiles, normCity, _loadFromText, geocode } = require('../src/geo');

test('haversineMiles: Phoenix to Tucson is ~110 mi', () => {
  const d = haversineMiles(33.4484, -112.074, 32.2226, -110.9747);
  assert.ok(d > 100 && d < 125, `got ${d}`);
});

test('normCity strips gazetteer suffixes and case', () => {
  assert.equal(normCity('Mesa city'), 'mesa');
  assert.equal(normCity('Queen Creek town'), 'queen creek');
  assert.equal(normCity('Saddlebrooke CDP'), 'saddlebrooke');
  assert.equal(normCity('  Los Angeles  '), 'los angeles');
});

test('lookup from tab-delimited gazetteer text (2023 format)', () => {
  const sample =
    'USPS\tGEOID\tANSICODE\tNAME\tLSAD\tFUNCSTAT\tALAND\tAWATER\tALAND_SQMI\tAWATER_SQMI\tINTPTLAT\tINTPTLONG\n' +
    'AZ\t0446000\t02410536\tMesa city\t25\tA\t1\t1\t1.0\t1.0\t33.401\t-111.717\n' +
    'CA\t0644000\t02410877\tLos Angeles city\t25\tA\t1\t1\t1.0\t1.0\t34.021\t-118.411\n';
  _loadFromText(sample);
  const m = geocode('Mesa', 'AZ');
  assert.ok(Math.abs(m.lat - 33.401) < 0.001);
  assert.equal(geocode('Nowheresville', 'AZ'), null);
  assert.ok(geocode('los angeles', 'ca'));
});

test('lookup from pipe-delimited gazetteer text (2025 format, extra GEOIDFQ col)', () => {
  const sample =
    'USPS|GEOID|GEOIDFQ|ANSICODE|NAME|LSAD|FUNCSTAT|ALAND|AWATER|ALAND_SQMI|AWATER_SQMI|INTPTLAT|INTPTLONG\n' +
    'AZ|0446000|1600000US0446000|02410536|Mesa city|25|A|1|1|1.0|1.0|33.401|-111.717\n';
  _loadFromText(sample);
  assert.ok(Math.abs(geocode('mesa', 'az').lon - -111.717) < 0.001);
});
