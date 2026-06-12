const fs = require('fs');
const path = require('path');
const cheerio = require('cheerio');
const config = require('../config');
const { politeFetch } = require('../http');

function searchUrl(region) {
  return `https://${region}.craigslist.org/search/cta?query=toyota+supra&min_auto_year=${config.MIN_YEAR}&max_auto_year=${config.MAX_YEAR}`;
}

// Craigslist server-renders <li class="cl-static-search-result"> for no-JS clients.
function parseSearchHtml(html, region, state) {
  const $ = cheerio.load(html);
  const out = [];
  $('li.cl-static-search-result').each((_, li) => {
    const a = $(li).find('a').first();
    const url = a.attr('href') || '';
    const idMatch = url.match(/\/(\d{8,})\.html/);
    if (!idMatch) return;
    const title = $(li).find('.title').text().trim() || $(li).attr('title') || '';
    const priceText = $(li).find('.price').text().replace(/[^0-9]/g, '');
    const locText = $(li).find('.location').text().trim();
    out.push({
      source: 'craigslist',
      sourceListingId: idMatch[1],
      url: url.startsWith('http') ? url : `https://${region}.craigslist.org${url}`,
      title,
      price: priceText ? parseInt(priceText, 10) : null,
      city: locText ? locText.replace(/[()]/g, '').split(',')[0].trim() : null,
      state,
      region,
      photoUrl: null, // static results carry no images; dashboard shows placeholder
      snippet: '',
      year: null,
      isAuction: false,
    });
  });
  return out;
}

function loadRegions() {
  const f = path.join(config.DATA_DIR, 'cl-regions.json');
  if (!fs.existsSync(f)) throw new Error('cl-regions.json missing - run `npm run setup`');
  return JSON.parse(fs.readFileSync(f, 'utf8'));
}

// Scrape the given region subdomains. Returns { candidates, coveredRegions }.
// One bad region never fails the scan; regions that error are excluded from
// coveredRegions so their listings aren't miss-counted. Throws only if ALL fail.
async function scrapeRegions(regionNames) {
  const all = loadRegions();
  const byName = new Map(all.map((r) => [r.region, r]));
  const candidates = [];
  const covered = [];
  let failures = 0;
  for (const name of regionNames) {
    const info = byName.get(name) || { state: null };
    try {
      const res = await politeFetch(searchUrl(name));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      candidates.push(...parseSearchHtml(await res.text(), name, info.state));
      covered.push(name);
    } catch (e) {
      failures++;
      console.warn(`[craigslist] ${name}: ${e.message}`);
    }
  }
  if (covered.length === 0 && regionNames.length > 0) throw new Error(`all ${failures} regions failed`);
  return { candidates, coveredRegions: covered };
}

const swRegions = () => config.SW_REGIONS;
const allRegionNames = () => loadRegions().map((r) => r.region);

module.exports = { parseSearchHtml, scrapeRegions, swRegions, allRegionNames, searchUrl };
