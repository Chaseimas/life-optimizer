const cheerio = require('cheerio');
const { politeFetch } = require('../http');

const SEARCH_URL = 'https://offerup.com/search?q=toyota%20supra';
const MANUAL_URL = SEARCH_URL;

function blockedError(status) {
  const e = new Error(`blocked (HTTP ${status})`);
  e.blocked = true;
  return e;
}

// OfferUp is a Next.js app - listings ride in <script id="__NEXT_DATA__">.
// The JSON shape shifts, so walk it for anything listing-shaped.
function parseNextData(html) {
  const $ = cheerio.load(html);
  const raw = $('#__NEXT_DATA__').text();
  if (!raw) return [];
  let data;
  try { data = JSON.parse(raw); } catch { return []; }
  const out = [];
  const seen = new Set();
  (function walk(node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) return node.forEach(walk);
    const id = node.listingId || node.id;
    if (id && node.title && node.price !== undefined && !seen.has(String(id))) {
      seen.add(String(id));
      const priceNum = parseFloat(String(node.price).replace(/[^0-9.]/g, ''));
      const locName = String(node.locationName || '');
      out.push({
        source: 'offerup',
        sourceListingId: String(id),
        url: node.listingUrl || (node.slug ? `https://offerup.com/item/detail/${node.slug}` : `https://offerup.com/item/detail/${id}`),
        title: String(node.title),
        price: isNaN(priceNum) ? null : Math.round(priceNum),
        city: locName ? locName.split(',')[0].trim() : null,
        state: /,\s*([A-Z]{2})\b/.test(locName) ? locName.match(/,\s*([A-Z]{2})\b/)[1] : null,
        region: null,
        photoUrl: (node.image && typeof node.image === 'object' ? node.image.url : node.image)
          || (node.photos && node.photos[0] && node.photos[0].detail && node.photos[0].detail.url) || null,
        snippet: '',
        year: null,
        isAuction: false,
      });
    }
    Object.values(node).forEach(walk);
  })(data);
  return out;
}

async function scrape() {
  const res = await politeFetch(SEARCH_URL);
  if (res.status === 403 || res.status === 429 || res.status === 503) throw blockedError(res.status);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const html = await res.text();
  if (/px-captcha|Access to this page has been denied|Just a moment/i.test(html)) throw blockedError(200);
  return { candidates: parseNextData(html), coveredRegions: null };
}

module.exports = { scrape, parseNextData, SEARCH_URL, MANUAL_URL };
