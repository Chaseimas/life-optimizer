const express = require('express');
const config = require('./config');
const { SOURCES } = require('./scrapers');
const { scoreDonor } = require('./score');
const buildPlan = require('./build-plan');

const VISIT_GAP_MS = 30 * 60e3; // a "visit" = first page load after 30+ min away

function makeApp(store) {
  const app = express();
  app.use(express.json());
  app.use(express.static(config.PUBLIC_DIR));

  app.get('/api/listings', (req, res) => {
    // NEW-badge bookkeeping: roll the visit window
    const now = Date.now();
    const cur = parseInt(store.getMeta('visit_current') || '0', 10);
    if (now - cur > VISIT_GAP_MS) {
      store.setMeta('visit_prev', cur || now);
    }
    store.setMeta('visit_current', now);
    const newSince = parseInt(store.getMeta('visit_prev') || '0', 10);

    const lastOk = Object.fromEntries(store.lastOkScans().map((r) => [r.source, r.last_ok]));
    const last = Object.fromEntries(store.lastScans().map((r) => [r.source, r]));
    const seen = new Set();
    const sources = [];
    for (const s of SOURCES) {
      if (seen.has(s.source)) continue;
      seen.add(s.source);
      sources.push({
        source: s.source,
        label: s.label.replace(/\s*\(.*\)$/, ''),
        lastOk: lastOk[s.source] || null,
        lastError: last[s.source] && !last[s.source].ok ? last[s.source].error_text : null,
        demoted: store.getMeta(`demoted:${s.source}`) === '1',
        manualUrl: s.manualUrl || null,
      });
    }

    res.json({
      listings: store.queryListings().map((l) => {
        const d = scoreDonor(l);
        return { ...l, donor_score: d.score, donor_tier: d.tier, donor_reasons: d.reasons };
      }),
      sources,
      newSince,
      home: config.HOME,
      tier2: config.TIER2_LINKS.map((t) => ({
        ...t,
        lastChecked: parseInt(store.getMeta(`checked:${t.key}`) || '0', 10) || null,
      })),
    });
  });

  app.post('/api/listings/:id/flag', (req, res) => {
    const { field, value } = req.body || {};
    try {
      store.setFlag(parseInt(req.params.id, 10), field, !!value);
      res.json({ ok: true });
    } catch (e) {
      res.status(400).json({ ok: false, error: e.message });
    }
  });

  app.post('/api/tier2/:key/checked', (req, res) => {
    store.setMeta(`checked:${req.params.key}`, Date.now());
    res.json({ ok: true });
  });

  app.get('/api/plan', (_req, res) => res.json(buildPlan));

  return app;
}

module.exports = { makeApp };
