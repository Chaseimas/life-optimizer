const config = require('./config');

let DELAY_MS = 2000;
let JITTER_MS = 1000;
const lastHit = new Map(); // host -> timestamp of last request

function _resetThrottle({ delayMs, jitterMs } = {}) {
  if (delayMs !== undefined) DELAY_MS = delayMs;
  if (jitterMs !== undefined) JITTER_MS = jitterMs;
  lastHit.clear();
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Fetch with: per-host politeness delay + jitter, browser headers, 30s timeout.
// Throws on network error; returns the Response (caller checks res.ok / res.status).
async function politeFetch(url, opts = {}) {
  const host = new URL(url).host;
  const now = Date.now();
  const wait = (lastHit.get(host) || 0) + DELAY_MS + Math.random() * JITTER_MS - now;
  if (wait > 0) await sleep(wait);
  lastHit.set(host, Date.now());

  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 30000);
  try {
    return await fetch(url, {
      redirect: 'follow',
      ...opts,
      signal: ac.signal,
      headers: {
        'User-Agent': config.USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        ...(opts.headers || {}),
      },
    });
  } finally {
    clearTimeout(timer);
  }
}

module.exports = { politeFetch, _resetThrottle };
