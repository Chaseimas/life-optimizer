const cheerio = require('cheerio');
const { politeFetch } = require('../http');
const { STATES, STATE_NAMES_BY_LENGTH } = require('./us-states');

const SEARCH_URL = 'https://classiccars.com/listings/find/1986-1992/toyota/supra';

// Listing URLs end like ".../1986-toyota-supra-for-sale-in-lutz-florida-33559".
// State names may be multi-word (new-york); non-US locations return nulls.
function locationFromSlug(url) {
  const m = String(url).match(/for-sale-in-(.+?)(?:-\d{5}(?:-\d{4})?)?$/);
  if (!m) return { city: null, state: null };
  const slug = m[1];
  for (const name of STATE_NAMES_BY_LENGTH) {
    const dashed = name.replace(/ /g, '-');
    if (slug === dashed) return { city: null, state: STATES[name] };
    if (slug.endsWith(`-${dashed}`)) {
      const city = slug.slice(0, -dashed.length - 1).replace(/-/g, ' ').trim();
      return { city: city || null, state: STATES[name] };
    }
  }
  return { city: null, state: null };
}

// Each listing is a <script type="application/ld+json"> with @type "car".
function parseSearchHtml(html) {
  const $ = cheerio.load(html);
  const out = [];
  $('script[type="application/ld+json"]').each((_, s) => {
    let it;
    try { it = JSON.parse($(s).text()); } catch { return; }
    if (!it || String(it['@type']).toLowerCase() !== 'car') return;
    const offers = it.offers || {};
    const relUrl = offers.url || '';
    if (!it.name || !relUrl) return;
    const idMatch = String(it.sku || '').match(/(\d{5,})/) || relUrl.match(/\/listings\/view\/(\d+)/);
    if (!idMatch) return;
    const loc = locationFromSlug(relUrl.split('?')[0]);
    out.push({
      source: 'classiccars',
      sourceListingId: idMatch[1],
      url: relUrl.startsWith('http') ? relUrl : `https://classiccars.com${relUrl}`,
      title: it.name,
      price: offers.price ? Math.round(Number(offers.price)) : null,
      city: loc.city,
      state: loc.state,
      region: null,
      photoUrl: it.image && it.image.url ? it.image.url : null,
      snippet: String(it.description || '').slice(0, 300),
      year: it.modelDate ? parseInt(it.modelDate, 10) : null,
      isAuction: false,
    });
  });
  return out;
}

async function scrape() {
  const res = await politeFetch(SEARCH_URL);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const candidates = parseSearchHtml(await res.text());
  if (candidates.length === 0) throw new Error('0 items parsed - page layout changed');
  return { candidates, coveredRegions: null };
}

module.exports = { parseSearchHtml, locationFromSlug, scrape, SEARCH_URL };
