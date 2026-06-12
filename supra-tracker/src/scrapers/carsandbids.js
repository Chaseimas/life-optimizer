const cheerio = require('cheerio');
const { politeFetch } = require('../http');

const SEARCH_URL = 'https://carsandbids.com/search?q=toyota%20supra';
const MANUAL_URL = SEARCH_URL;

function blockedError(status) {
  const e = new Error(`blocked (HTTP ${status})`);
  e.blocked = true;
  return e;
}

async function scrape() {
  const res = await politeFetch(SEARCH_URL);
  if (res.status === 403 || res.status === 429 || res.status === 503) throw blockedError(res.status);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const html = await res.text();
  // Cloudflare interstitials sometimes come back as 200 - treat as blocked
  if (/cf-browser-verification|challenge-platform|Just a moment/i.test(html)) throw blockedError(200);
  const $ = cheerio.load(html);
  const out = [];
  $('a[href*="/auctions/"]').each((_, a) => {
    const href = $(a).attr('href') || '';
    const idMatch = href.match(/\/auctions\/([A-Za-z0-9]+)\//);
    const title = $(a).find('.auction-title').text().trim() || $(a).attr('title') || '';
    if (!idMatch || title.length < 4 || !/supra/i.test(title)) return;
    out.push({
      source: 'carsandbids',
      sourceListingId: idMatch[1],
      url: href.startsWith('http') ? href : `https://carsandbids.com${href}`,
      title,
      price: null,
      city: null, state: null, region: null,
      photoUrl: $(a).find('img').attr('src') || null,
      snippet: '',
      year: null,
      isAuction: true,
    });
  });
  return { candidates: out, coveredRegions: null };
}

module.exports = { scrape, SEARCH_URL, MANUAL_URL };
