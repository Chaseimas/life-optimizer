const cheerio = require('cheerio');
const { politeFetch } = require('../http');
const { STATES } = require('./us-states');

// eBay 403-blocks non-browser TLS fingerprints (verified 2026-06), so this source
// is registered demotable: it keeps attempting politely and the scheduler demotes
// it to a manual link after repeated blocks. Self-heals if eBay unblocks.
const SEARCH_URL =
  'https://www.ebay.com/sch/i.html?_nkw=toyota+supra&_sacat=6001&_ipg=60';
const MANUAL_URL = SEARCH_URL.replace('&_ipg=60', '');

function parseLocation(text) {
  // "from Tempe, Arizona" / "Located in Tempe, Arizona" -> { city, state }
  const m = String(text || '').match(/(?:from|in)\s+([^,]+),\s*([A-Za-z .]+)$/i);
  if (!m) return { city: null, state: null };
  const st = STATES[m[2].trim().toLowerCase()];
  return st ? { city: m[1].trim(), state: st } : { city: null, state: null };
}

function blockedError(status) {
  const e = new Error(`blocked (HTTP ${status})`);
  e.blocked = true;
  return e;
}

function parseSearchHtml(html) {
  const $ = cheerio.load(html);
  const out = [];
  $('.s-item').each((_, el) => {
    const title = $(el).find('.s-item__title').first().text().trim();
    if (!title || title === 'Shop on eBay') return; // skeleton/ad item
    const url = ($(el).find('a.s-item__link').attr('href') || '').split('?')[0];
    const idMatch = url.match(/\/itm\/(\d+)/);
    if (!idMatch) return;
    const priceText = $(el).find('.s-item__price').first().text().replace(/[^0-9.]/g, '');
    const loc = parseLocation($(el).find('.s-item__location, .s-item__itemLocation').first().text());
    out.push({
      source: 'ebay',
      sourceListingId: idMatch[1],
      url,
      title,
      price: priceText ? Math.round(parseFloat(priceText)) : null,
      city: loc.city,
      state: loc.state,
      region: null,
      photoUrl: $(el).find('.s-item__image-wrapper img, .s-item__image img').attr('src') || null,
      snippet: $(el).find('.s-item__subtitle').text().trim(),
      year: null,
      isAuction: $(el).find('.s-item__bids, .s-item__bidCount').length > 0,
    });
  });
  return out;
}

async function scrape() {
  const res = await politeFetch(SEARCH_URL);
  if (res.status === 403 || res.status === 429 || res.status === 503) throw blockedError(res.status);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const html = await res.text();
  if (/Pardon our interruption|challenge-platform|Reference ID/i.test(html)) throw blockedError(200);
  const candidates = parseSearchHtml(html);
  if (candidates.length === 0) throw new Error('0 items parsed - page layout changed or soft block');
  return { candidates, coveredRegions: null };
}

module.exports = { parseSearchHtml, scrape, SEARCH_URL, MANUAL_URL };
