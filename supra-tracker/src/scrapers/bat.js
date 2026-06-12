const cheerio = require('cheerio');
const { politeFetch } = require('../http');

// All-generations Supra page; the year matcher keeps only 1986-1992 A70s.
// (BaT has no MK3-specific page slug as of 2026-06.)
const PAGE_URL = 'https://bringatrailer.com/toyota/supra/';

// Live auctions appear two ways:
//  1. Server-rendered <div class="listing-card" data-listing_id="..."> cards
//     (a Knockout template card also exists - it has no real href, so it's skipped).
//  2. On busier pages, a `var auctionsCurrentInitialData = {...}` JSON blob with items[].
function parseModelPage(html) {
  const $ = cheerio.load(html);
  const byId = new Map();

  $('div.listing-card').each((_, el) => {
    const id = $(el).attr('data-listing_id');
    const a = $(el).find('h3 a').first();
    const url = a.attr('href') || '';
    if (!id || !/\/listing\//.test(url)) return; // skips the KO template card
    byId.set(String(id), {
      source: 'bat',
      sourceListingId: String(id),
      url,
      title: a.text().trim(),
      price: null, // live bid arrives via websocket; not in static HTML
      city: null,  // BaT shows location only on detail pages
      state: null,
      region: null,
      photoUrl: $(el).find('.thumbnail img').attr('src') || null,
      snippet: '',
      year: null,
      isAuction: true,
    });
  });

  const m = html.match(/auctionsCurrentInitialData\s*=\s*(\{[\s\S]*?\});\s*\n/);
  if (m) {
    try {
      const data = JSON.parse(m[1]);
      for (const it of data.items || []) {
        if (!it.url || !it.title) continue;
        const id = String(it.id || it.url);
        if (byId.has(id)) continue;
        byId.set(id, {
          source: 'bat',
          sourceListingId: id,
          url: it.url,
          title: String(it.title).replace(/<[^>]*>/g, ''),
          price: it.current_bid ? Math.round(Number(it.current_bid)) : null,
          city: null,
          state: null,
          region: null,
          photoUrl: it.thumbnail_url || null,
          snippet: '',
          year: null,
          isAuction: true,
        });
      }
    } catch { /* malformed blob - DOM cards already captured */ }
  }

  return [...byId.values()];
}

async function scrape() {
  const res = await politeFetch(PAGE_URL);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return { candidates: parseModelPage(await res.text()), coveredRegions: null };
}

module.exports = { parseModelPage, scrape, PAGE_URL };
