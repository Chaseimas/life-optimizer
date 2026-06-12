const cheerio = require('cheerio');
const { politeFetch } = require('../http');

// Hemmings is Cloudflare-blocked for non-browser clients (verified 2026-06), so
// this source is registered demotable. Parser targets schema.org JSON-LD, the
// same pattern ClassicCars uses; revisit against a live capture if it unblocks.
const SEARCH_URL = 'https://www.hemmings.com/classifieds/cars-for-sale/toyota/supra';
const MANUAL_URL = SEARCH_URL;

function blockedError(status) {
  const e = new Error(`blocked (HTTP ${status})`);
  e.blocked = true;
  return e;
}

function splitLocation(text) {
  // "Phoenix, AZ" / "Phoenix, Arizona 85001" -> {city, state}
  const m = String(text || '').trim().match(/^([^,]+),\s*([A-Z]{2})\b/);
  return m ? { city: m[1].trim(), state: m[2] } : { city: null, state: null };
}

function parseSearchHtml(html) {
  const $ = cheerio.load(html);
  const out = [];
  $('script[type="application/ld+json"]').each((_, s) => {
    let data;
    try { data = JSON.parse($(s).text()); } catch { return; }
    const arr = Array.isArray(data) ? data : data['@graph'] || [data];
    for (const node of arr) {
      const items = node.itemListElement ? node.itemListElement.map((e) => e.item || e) : [node];
      for (const it of items) {
        if (!it || !it.url || !it.name) continue;
        if (!/vehicle|product|car/i.test(String(it['@type'] || ''))) continue;
        const idMatch = String(it.url).match(/(\d{5,})/);
        const offers = it.offers || {};
        out.push({
          source: 'hemmings',
          sourceListingId: idMatch ? idMatch[1] : it.url,
          url: it.url.startsWith('http') ? it.url : `https://www.hemmings.com${it.url}`,
          title: it.name,
          price: offers.price ? Math.round(Number(offers.price)) : null,
          ...splitLocation(offers.areaServed || it.areaServed),
          region: null,
          photoUrl: typeof it.image === 'string' ? it.image : (Array.isArray(it.image) ? it.image[0] : (it.image && it.image.url) || null),
          snippet: String(it.description || '').slice(0, 300),
          year: it.vehicleModelDate || it.modelDate ? parseInt(it.vehicleModelDate || it.modelDate, 10) : null,
          isAuction: false,
        });
      }
    }
  });
  return out;
}

async function scrape() {
  const res = await politeFetch(SEARCH_URL);
  if (res.status === 403 || res.status === 429 || res.status === 503) throw blockedError(res.status);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const html = await res.text();
  if (/cf-browser-verification|challenge-platform|Just a moment/i.test(html)) throw blockedError(200);
  return { candidates: parseSearchHtml(html), coveredRegions: null };
}

module.exports = { parseSearchHtml, scrape, SEARCH_URL, MANUAL_URL };
