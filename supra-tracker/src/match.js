const { MIN_YEAR, MAX_YEAR } = require('./config');

// 4-digit 1980-1999 or apostrophe-two-digit ('86..'92 etc).
function extractYear(text) {
  const t = String(text || '');
  const four = t.match(/\b(19[8-9]\d)\b/);
  if (four) return parseInt(four[1], 10);
  const two = t.match(/['‘’](8[0-9]|9[0-9])\b/);
  if (two) return 1900 + parseInt(two[1], 10);
  return null;
}

const NON_TURBO_RX = [
  /non[\s-]?turbo/gi,
  /\bn\/?a\b/gi,          // standalone NA / N/A
  /\b7m[\s-]?ge\b/gi,     // 7M-GE (the \b after 'ge' keeps 7mgte from matching)
];
const TURBO_RX = [
  /turbo/i,               // catches turbo, turbocharged, twin turbo, targa turbo
  /7m[\s-]?gte/i,
  /\b1jz/i,
];
const MK3_RX = /mk[\s-]?(3|iii)\b|mkiii|\ba70\b|mark[\s-]?(3|iii)\b/i;

function classifyTurbo(text) {
  let t = ` ${String(text || '')} `;
  let hasNA = false;
  for (const rx of NON_TURBO_RX) {
    if (rx.test(t)) {
      hasNA = true;
      t = t.replace(rx, ' ');  // remove so "non-turbo" can't trip the turbo check
    }
    rx.lastIndex = 0;
  }
  const hasTurbo = TURBO_RX.some((rx) => rx.test(t));
  if (hasTurbo && hasNA) return 'unconfirmed';
  if (hasTurbo) return 'confirmed';
  if (hasNA) return 'non_turbo';
  return 'unconfirmed';
}

// Decide whether a raw candidate is an A70 we keep.
// Returns { accept, year, turboStatus, reason }
function evaluateCandidate(c) {
  const text = `${c.title || ''} ${c.snippet || ''}`;
  const year = c.year || extractYear(text);
  const turboStatus = classifyTurbo(text);
  // Site search is fuzzy (a "toyota supra" query returns Venzas and Camrys too)
  if (!/supra/i.test(text)) {
    return { accept: false, year, turboStatus, reason: 'not a supra' };
  }
  if (year !== null && year !== undefined) {
    if (year < MIN_YEAR || year > MAX_YEAR) {
      return { accept: false, year, turboStatus, reason: `year ${year} outside ${MIN_YEAR}-${MAX_YEAR}` };
    }
    return { accept: true, year, turboStatus, reason: 'year in range' };
  }
  if (MK3_RX.test(text)) {
    return { accept: true, year: null, turboStatus, reason: 'no year, MK3 keyword' };
  }
  return { accept: false, year: null, turboStatus, reason: 'no year, no MK3 keyword' };
}

module.exports = { extractYear, classifyTurbo, evaluateCandidate };
