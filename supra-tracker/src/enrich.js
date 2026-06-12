const cheerio = require('cheerio');
const { politeFetch } = require('./http');

// Search results only carry titles; the keywords that matter for donor scoring
// ("rust free", "needs engine", "clean title") live in the ad body. This fetches
// each new CL/OfferUp listing's detail page once and stores the full text.
const CAP = 4000;

function parseClBody(html) {
  const $ = cheerio.load(html);
  const body = $('#postingbody');
  if (!body.length) return null;
  const text = body.text().replace(/QR Code Link to This Post/gi, ' ').replace(/\s+/g, ' ').trim();
  return text ? text.slice(0, CAP) : null;
}

function parseOfferUpBody(html) {
  const $ = cheerio.load(html);
  const raw = $('#__NEXT_DATA__').text();
  if (!raw) return null;
  let data;
  try { data = JSON.parse(raw); } catch { return null; }
  let found = null;
  (function walk(node) {
    if (!node || typeof node !== 'object' || found) return;
    if (Array.isArray(node)) return node.forEach(walk);
    if (typeof node.description === 'string' && node.description.length > 10 && (node.title || node.listingId)) {
      found = node.description;
      return;
    }
    Object.values(node).forEach(walk);
  })(data);
  return found ? found.replace(/\s+/g, ' ').trim().slice(0, CAP) : null;
}

async function fetchDescription(source, url) {
  try {
    const res = await politeFetch(url);
    if (!res.ok) return null;
    const html = await res.text();
    return source === 'craigslist' ? parseClBody(html) : parseOfferUpBody(html);
  } catch {
    return null;
  }
}

// One polite detail fetch per listing that still lacks ad text. Failures store ''
// (sentinel: tried, unavailable) so nothing is retried forever.
async function enrichBatch(store, limit = 10) {
  const todo = store.listNeedingDescription(limit);
  for (const row of todo) {
    const text = await fetchDescription(row.source, row.url);
    store.setDescription(row.id, text || '');
    if (text) console.log(`[enrich] ${row.source} #${row.id}: ${text.length} chars`);
  }
  return todo.length;
}

module.exports = { parseClBody, parseOfferUpBody, fetchDescription, enrichBatch };
