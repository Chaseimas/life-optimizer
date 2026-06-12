# Donor Mode + Build Plan Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score every tracked A70 as a 2JZ-swap donor (price fit $1k–$9k, location-aware rust, chassis-deal logic), show it behind a 🔧 Donor mode toggle, enrich CL/OfferUp listings with full ad text, and add a read-only Build Plan page.

**Architecture:** New pure `src/score.js` computes scores live in the API (nothing stored). New `src/enrich.js` fetches full ad text once per new CL/OfferUp listing after scans. `listings` gains a `description` column via try/catch ALTER migration. Build plan data is one data file feeding `/api/plan` and `public/build-plan.html`.

**Tech Stack:** Existing: Node 24, express, better-sqlite3 ^12, cheerio, node:test.

**Spec:** `docs/superpowers/specs/2026-06-12-supra-donor-mode-design.md`

**Working dir:** all commands run from `supra-tracker/`. The deployed Windows task "SupraTracker" runs the OLD code until Task 5 restarts it.

---

### Task 1: Donor scoring (`src/score.js`)

**Files:**
- Create: `supra-tracker/src/score.js`
- Modify: `supra-tracker/src/config.js` (add `DONOR` block)
- Test: `supra-tracker/test/score.test.js`

- [ ] **Step 1: Add DONOR config**

In `src/config.js`, after `PREFERRED_YEAR: 1991,` add:

```js
  // Donor-mode scoring (2JZ-swap build: chassis matters, engine doesn't)
  DONOR: {
    budgetMin: 1000,
    budgetMax: 9000,
    deadEngineCheapMax: 6000,  // dead engine at/below this = donor deal
    deadEngineHighMin: 9000,   // dead engine above this = priced like a runner
    dryStates: ['AZ', 'NM', 'NV', 'CA', 'TX', 'UT', 'CO'],
  },
```

- [ ] **Step 2: Write the failing tests**

`supra-tracker/test/score.test.js`:

```js
const test = require('node:test');
const assert = require('node:assert');
const { scoreDonor } = require('../src/score');

const L = (over = {}) => ({
  title: '1989 Toyota Supra', snippet: '', description: '',
  price: 5000, state: 'OH', turbo_status: 'unconfirmed', ...over,
});

const has = (r, txt) => r.reasons.some((x) => x.text.includes(txt));

test('price bands', () => {
  assert.ok(has(scoreDonor(L({ price: 5000 })), 'in Phase-1 budget'));
  assert.ok(has(scoreDonor(L({ price: 800 })), 'suspiciously cheap'));
  assert.ok(has(scoreDonor(L({ price: 10000 })), 'slightly over'));
  assert.ok(has(scoreDonor(L({ price: 15000 })), 'over budget'));
  assert.ok(has(scoreDonor(L({ price: 46000 })), 'way over budget'));
  assert.ok(has(scoreDonor(L({ price: null })), 'no price'));
});

test('rust: positive, structural, cosmetic, generic precedence', () => {
  const pos = scoreDonor(L({ description: 'rust free arizona car, solid floors' }));
  assert.ok(has(pos, 'rust-free / solid'));
  assert.ok(!has(pos, 'rust mentioned'), 'positive must not double-count as generic');
  assert.ok(!has(pos, 'structural'), '"solid floors"+"no rot" style text must not look structural');

  const struct = scoreDonor(L({ description: 'some rust in the rocker panels' }));
  assert.ok(has(struct, 'structural rust'));
  assert.ok(!has(struct, 'rust mentioned'), 'structural suppresses generic');

  const cosm = scoreDonor(L({ description: 'minor surface rust on the hood' }));
  assert.ok(has(cosm, 'cosmetic rust'));
  assert.ok(!has(cosm, 'rust mentioned'), 'cosmetic suppresses generic');

  const gen = scoreDonor(L({ description: 'has some rust, runs great' }));
  assert.ok(has(gen, 'rust mentioned'));

  // "rotors" must not trip rust/rot rules
  const rotor = scoreDonor(L({ description: 'new brake rotors and floors carpets' }));
  assert.ok(!has(rotor, 'structural') && !has(rotor, 'rust mentioned'));
});

test('title status + condition cap', () => {
  assert.ok(has(scoreDonor(L({ description: 'clean title in hand' })), 'clean title'));
  assert.ok(has(scoreDonor(L({ description: 'salvage title' })), 'branded/missing title'));
  const kept = scoreDonor(L({ description: 'garage kept, original paint, one owner, straight body' }));
  const condDeltas = kept.reasons.filter((r) => r.text.includes('well-kept'));
  assert.equal(condDeltas.length, 1);
  assert.ok(condDeltas[0].delta <= 10);
});

test('dead-engine donor logic gated by price', () => {
  assert.ok(has(scoreDonor(L({ price: 4000, description: 'blown engine, doesnt run' })), 'donor deal'));
  assert.ok(has(scoreDonor(L({ price: 12000, description: 'needs engine' })), 'priced like a runner'));
  assert.ok(has(scoreDonor(L({ price: 8000, description: 'engine out, roller' })), 'engine condition irrelevant'));
  assert.ok(has(scoreDonor(L({ description: 'parting out, parts car' })), 'parts car'));
});

test('frame damage, dry state, non-turbo bonus', () => {
  assert.ok(has(scoreDonor(L({ description: 'frame damage from accident' })), 'frame/accident'));
  assert.ok(has(scoreDonor(L({ state: 'AZ' })), 'dry-climate'));
  assert.ok(has(scoreDonor(L({ turbo_status: 'non_turbo' })), 'non-turbo'));
});

test('score clamps 0-100 and tiers map', () => {
  const great = scoreDonor(L({ price: 5000, state: 'AZ', description: 'rust free, clean title, garage kept' }));
  assert.ok(great.score >= 70 && great.tier === 'great', `got ${great.score}`);
  const poor = scoreDonor(L({ price: 46000, description: 'rust in floor pans, salvage title, wrecked' }));
  assert.ok(poor.score < 50 && poor.tier === 'poor', `got ${poor.score}`);
  assert.ok(poor.score >= 0);
  const mid = scoreDonor(L({}));
  assert.ok(['possible', 'great', 'poor'].includes(mid.tier));
  // reasons sorted by |delta| descending
  const r = great.reasons.map((x) => Math.abs(x.delta));
  assert.deepEqual(r, [...r].sort((a, b) => b - a));
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `node --test test/score.test.js`
Expected: FAIL — cannot find module `../src/score`.

- [ ] **Step 4: Write src/score.js**

```js
const { DONOR } = require('./config');

// Positive phrases stripped before negative checks so "no rust" can't count as rust.
const POS_RX = /rust[- ]?free|no rust|zero rust|no rot\b|solid floors?|solid frame|solid underneath/g;
const STRUCT_WORDS = '(?:frame|rails?|rockers?|floors?|pans?|strut|towers?|quarters?|arch(?:es)?|hatch|underneath|undercarriage)';
const RUST_WORD = '(?:rust(?:y|ed)?|rot(?:ted|ten)?)';
const STRUCT_RX = new RegExp(`${STRUCT_WORDS}[^.]{0,40}?\\b${RUST_WORD}\\b|\\b${RUST_WORD}\\b[^.]{0,40}?${STRUCT_WORDS}`);
const COSM_RX = /surface rust|minor rust|light rust|little rust|rust bubbles?|bubbling/g;
const GENERIC_RX = new RegExp(`\\b${RUST_WORD}\\b`);
const DEAD_RX = /needs engine|no engine|engine out|no motor|blown|bad engine|knock|doesn'?t run|does not run|not running|won'?t start|roller\b/;
const COND_RX = [/garage kept|garaged/, /original paint/, /straight body/, /\b(one|1) owner/, /adult owned/, /always covered/, /(all|bone) stock/];

function scoreDonor(l) {
  const text = `${l.title || ''} ${l.snippet || ''} ${l.description || ''}`.toLowerCase();
  const reasons = [];
  const add = (delta, t) => reasons.push({ delta, text: t });

  // Price vs Phase-1 budget
  const p = l.price;
  if (p == null) add(-5, 'no price listed');
  else if (p < DONOR.budgetMin) add(5, "suspiciously cheap — verify it's real");
  else if (p <= DONOR.budgetMax) add(20, 'in Phase-1 budget');
  else if (p <= 12000) add(6, 'slightly over budget');
  else if (p <= 18000) add(-8, 'over budget');
  else add(-20, 'way over budget for a donor');

  // Rust (location-aware)
  if (POS_RX.test(text)) add(15, 'says rust-free / solid');
  POS_RX.lastIndex = 0;
  const neg = text.replace(POS_RX, ' ');           // strip positives
  const hasStruct = STRUCT_RX.test(neg);
  const hasCosm = COSM_RX.test(neg);
  COSM_RX.lastIndex = 0;
  const negNoCosm = neg.replace(COSM_RX, ' ');
  if (hasStruct) add(-25, 'structural rust mentioned (frame/rockers/floors area)');
  if (hasCosm) add(-6, 'cosmetic rust only');
  if (!hasStruct && !hasCosm && GENERIC_RX.test(negNoCosm)) add(-12, 'rust mentioned');

  // Title status
  if (/clean title/.test(text)) add(10, 'clean title');
  if (/salvage|rebuilt title|branded title|no title|bill of sale/.test(text)) add(-15, 'branded/missing title');

  // Condition positives, capped
  const condHits = COND_RX.filter((rx) => rx.test(text)).length;
  if (condHits > 0) add(Math.min(condHits * 5, 10), 'well-kept signals');

  // Dead engine = fine for a swap, if the price agrees
  if (/parts car|parting out/.test(text)) add(-15, 'parts car');
  else if (DEAD_RX.test(text)) {
    if (p != null && p <= DONOR.deadEngineCheapMax) add(12, "donor deal: cheap chassis, engine's getting swapped anyway");
    else if (p != null && p > DONOR.deadEngineHighMin) add(-8, 'not running but priced like a runner');
    else add(4, 'engine condition irrelevant for swap');
  }

  if (/frame damage|frame rot|bent frame|wrecked|accident|front end damage/.test(text)) add(-15, 'frame/accident damage mentioned');
  if (l.state && DONOR.dryStates.includes(l.state)) add(6, 'dry-climate car');
  if (l.turbo_status === 'non_turbo') add(4, "non-turbo = cheaper chassis, engine's going anyway");

  const score = Math.max(0, Math.min(100, 50 + reasons.reduce((s, r) => s + r.delta, 0)));
  const tier = score >= 70 ? 'great' : score >= 50 ? 'possible' : 'poor';
  reasons.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
  return { score, tier, reasons };
}

module.exports = { scoreDonor };
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `node --test test/score.test.js`
Expected: PASS — 6 tests. If a precedence test fails, fix the regex/stripping order in score.js (the tests are the contract).

- [ ] **Step 6: Commit**

```bash
git add supra-tracker/src/score.js supra-tracker/src/config.js supra-tracker/test/score.test.js
git commit -m "supra-tracker: donor scoring (budget fit + location-aware rust + swap logic)"
```

---

### Task 2: `description` column migration + scrapers that already have descriptions store them

**Files:**
- Modify: `supra-tracker/src/db.js` (migration)
- Modify: `supra-tracker/src/store.js` (insert/update description)
- Modify: `supra-tracker/src/scrapers/classiccars.js`, `supra-tracker/src/scrapers/hemmings.js` (pass full description)
- Test: `supra-tracker/test/db.test.js`, `supra-tracker/test/store.test.js` (extend)

- [ ] **Step 1: Write the failing migration test**

Append to `supra-tracker/test/db.test.js`:

```js
test('migration: description column exists even on a db created without it', () => {
  const db = createDb(':memory:');
  const cols = db.prepare("PRAGMA table_info(listings)").all().map((c) => c.name);
  assert.ok(cols.includes('description'));
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test test/db.test.js`
Expected: FAIL — `description` not in columns.

- [ ] **Step 3: Add migration in src/db.js**

In `createDb`, after `db.exec(SCHEMA);` add:

```js
  // Migrations for dbs created before these columns existed (no-op when present)
  try { db.exec('ALTER TABLE listings ADD COLUMN description TEXT'); } catch { /* exists */ }
```

(Leave SCHEMA itself unchanged — the ALTER covers both fresh and existing databases identically.)

- [ ] **Step 4: Write the failing store test**

Append to `supra-tracker/test/store.test.js`:

```js
test('ingest stores description when the scraper provides one; setDescription updates turbo', () => {
  const store = makeStore(createDb(':memory:'));
  store.ingestScan('classiccars', [cand({
    source: 'classiccars', sourceListingId: 'cc1',
    description: 'Body is rust free. This is the non turbo model.',
    title: '1988 Toyota Supra',
  })], null);
  let l = store.allListings()[0];
  assert.match(l.description, /rust free/);

  // enrichment path: description arrives later and upgrades turbo_status
  store.ingestScan('craigslist', [cand({ sourceListingId: 'cl1', title: '1990 Toyota Supra clean' })], ['phoenix']);
  l = store.allListings().find((x) => x.source_listing_id === 'cl1');
  assert.equal(l.turbo_status, 'unconfirmed');
  store.setDescription(l.id, 'Original 7M-GTE turbo runs strong, rust free underneath');
  l = store.allListings().find((x) => x.source_listing_id === 'cl1');
  assert.match(l.description, /7M-GTE/i);
  assert.equal(l.turbo_status, 'confirmed');

  // failure sentinel: empty string stored, turbo untouched
  store.setDescription(l.id, '');
  assert.equal(store.allListings().find((x) => x.source_listing_id === 'cl1').description, '');
});
```

- [ ] **Step 5: Run to verify it fails**

Run: `node --test test/store.test.js`
Expected: FAIL — `description` not stored / `setDescription` not a function.

- [ ] **Step 6: Implement in src/store.js**

a) Add to the require block at top:

```js
const { evaluateCandidate, classifyTurbo } = require('./match');
```

(replacing the existing `const { evaluateCandidate } = require('./match');`)

b) In `insL`, add `description` to the column list and values:

```js
  const insL = db.prepare(`INSERT INTO listings
    (source, source_listing_id, url, title, year, price, city, state, region,
     lat, lon, distance_mi, photo_url, snippet, description, turbo_status, is_auction,
     first_seen, last_seen)
    VALUES (@source, @sourceListingId, @url, @title, @year, @price, @city, @state, @region,
     @lat, @lon, @distanceMi, @photoUrl, @snippet, @description, @turboStatus, @isAuction,
     @now, @now)`);
```

c) In the sanitize block inside `ingestScan`, add after `snippet`:

```js
          description: str(raw.description),
```

d) In the `insL.run({...})` call add `description: c.description,` after `snippet: c.snippet,`.

e) Add to the returned store object:

```js
    setDescription: (id, desc) => {
      const text = String(desc ?? '');
      db.prepare('UPDATE listings SET description=? WHERE id=?').run(text, id);
      if (text) {
        const row = db.prepare('SELECT title FROM listings WHERE id=?').get(id);
        if (row) db.prepare('UPDATE listings SET turbo_status=? WHERE id=?')
          .run(classifyTurbo(`${row.title} ${text}`), id);
      }
    },
    listNeedingDescription: (limit) => db.prepare(`
      SELECT id, source, url, title FROM listings
      WHERE description IS NULL AND source IN ('craigslist','offerup') AND status='active'
      ORDER BY first_seen DESC LIMIT ?`).all(limit),
```

- [ ] **Step 7: Pass descriptions through from classiccars + hemmings**

In `src/scrapers/classiccars.js`, in the `out.push({...})`, after `snippet: ...` add:

```js
          description: String(it.description || '').slice(0, 4000),
```

In `src/scrapers/hemmings.js`, same addition after its `snippet:` line:

```js
          description: String(it.description || '').slice(0, 4000),
```

- [ ] **Step 8: Run db + store tests to verify they pass**

Run: `node --test test/db.test.js test/store.test.js`
Expected: PASS (3 + 8 tests).

- [ ] **Step 9: Commit**

```bash
git add supra-tracker/src/db.js supra-tracker/src/store.js supra-tracker/src/scrapers/classiccars.js supra-tracker/src/scrapers/hemmings.js supra-tracker/test/db.test.js supra-tracker/test/store.test.js
git commit -m "supra-tracker: description column + storage, turbo reclassify on enrich"
```

---

### Task 3: Ad-text enrichment (`src/enrich.js`)

**Files:**
- Create: `supra-tracker/src/enrich.js`
- Create: `supra-tracker/test/fixtures/cl-detail.html`, `supra-tracker/test/fixtures/offerup-detail.html` (live captures)
- Modify: `supra-tracker/src/scheduler.js`, `supra-tracker/scripts/scan-once.js` (wire in)
- Test: `supra-tracker/test/enrich.test.js`

- [ ] **Step 1: Capture live fixtures**

Pick a current listing URL of each type straight from the live db:

```powershell
node -e "const {getDb}=require('./src/db');const rows=getDb().prepare(`SELECT source,url FROM listings WHERE source IN ('craigslist','offerup') AND status='active'`).all();console.log(rows.map(r=>r.source+' '+r.url).join('\n'))"
```

Then (substituting two real URLs from the output):

```powershell
node scripts/fetch-fixture.js "<a craigslist listing url>" test/fixtures/cl-detail.html
node scripts/fetch-fixture.js "<an offerup listing url>" test/fixtures/offerup-detail.html
```

Inspect: `cl-detail.html` must contain `id="postingbody"`; `offerup-detail.html` must contain `__NEXT_DATA__` with a `description` field. If OfferUp's detail page blocks (403/captcha-page), note it, skip the OfferUp fixture + its test assertion, and let `fetchDescription` return null for it at runtime (the sentinel handles it).

- [ ] **Step 2: Write the failing tests**

`supra-tracker/test/enrich.test.js`:

```js
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { parseClBody, parseOfferUpBody } = require('../src/enrich');

const fix = (f) => fs.readFileSync(path.join(__dirname, 'fixtures', f), 'utf8');

test('parses craigslist #postingbody text', () => {
  const text = parseClBody(fix('cl-detail.html'));
  assert.ok(text && text.length > 30, `got: ${text && text.slice(0, 80)}`);
  assert.ok(!text.includes('QR Code Link to This Post'));
});

test('parses offerup detail description', () => {
  let html;
  try { html = fix('offerup-detail.html'); } catch { return; } // fixture skipped if blocked
  const text = parseOfferUpBody(html);
  assert.ok(text && text.length > 10, `got: ${text && text.slice(0, 80)}`);
});

test('parsers return null on junk html', () => {
  assert.equal(parseClBody('<html><body>nope</body></html>'), null);
  assert.equal(parseOfferUpBody('<html><body>nope</body></html>'), null);
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `node --test test/enrich.test.js`
Expected: FAIL — cannot find module `../src/enrich`.

- [ ] **Step 4: Write src/enrich.js**

```js
const cheerio = require('cheerio');
const { politeFetch } = require('./http');

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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `node --test test/enrich.test.js`
Expected: PASS (adapt selectors to the real fixtures if needed — fixtures are the truth).

- [ ] **Step 6: Wire into scheduler and scan-once**

In `src/scheduler.js`: add `const { enrichBatch } = require('./enrich');` at top, and in `runEntry` success path after the `console.log` line add:

```js
    if (entry.source === 'craigslist' || entry.source === 'offerup') {
      await enrichBatch(store).catch((e) => console.warn(`[enrich] ${e.message}`));
    }
```

In `scripts/scan-once.js`: add `const { enrichBatch } = require('../src/enrich');` to the requires, and after the `for (const e of entries) await runEntry(e, store);` line add:

```js
  const enriched = await enrichBatch(store, 25);
  if (enriched) console.log(`enriched ${enriched} listings with full ad text`);
```

- [ ] **Step 7: Live verification**

Run: `npm run scan -- craigslist-sw`
Expected: scan output then `[enrich] craigslist #N: ...` lines (existing CL/OfferUp rows have NULL descriptions, so the first batch enriches up to 25). Verify:

```powershell
node -e "const {getDb}=require('./src/db');const r=getDb().prepare(`SELECT source,COUNT(*) n, SUM(description IS NOT NULL) filled FROM listings GROUP BY source`).all();console.log(r)"
```

Expected: craigslist/offerup rows show `filled` > 0.

- [ ] **Step 8: Commit**

```bash
git add supra-tracker/src/enrich.js supra-tracker/test/enrich.test.js supra-tracker/test/fixtures/cl-detail.html supra-tracker/src/scheduler.js supra-tracker/scripts/scan-once.js
git add supra-tracker/test/fixtures/offerup-detail.html 2>$null
git commit -m "supra-tracker: full ad-text enrichment for craigslist + offerup"
```

---

### Task 4: Build plan data + API donor fields

**Files:**
- Create: `supra-tracker/src/build-plan.js`
- Modify: `supra-tracker/src/api.js`
- Test: `supra-tracker/test/api.test.js` (extend)

- [ ] **Step 1: Write the failing test**

Append to `supra-tracker/test/api.test.js`:

```js
test('listings carry donor fields; /api/plan returns 9 phases', async () => {
  const store = makeStore(createDb(':memory:'));
  seed(store);
  const app = makeApp(store);
  const srv = app.listen(0);
  const base = `http://127.0.0.1:${srv.address().port}`;
  const body = await (await fetch(`${base}/api/listings`)).json();
  const l = body.listings[0];
  assert.ok(typeof l.donor_score === 'number');
  assert.ok(['great', 'possible', 'poor'].includes(l.donor_tier));
  assert.ok(Array.isArray(l.donor_reasons) && l.donor_reasons.length > 0);

  const plan = await (await fetch(`${base}/api/plan`)).json();
  assert.equal(plan.phases.length, 9);
  assert.ok(plan.phases[0].name.toLowerCase().includes('buy'));
  assert.equal(plan.finals.length, 3);
  srv.close();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test test/api.test.js`
Expected: FAIL — `donor_score` undefined.

- [ ] **Step 3: Write src/build-plan.js**

Kase's plan, transcribed exactly (costs as display strings):

```js
// Kase's MK3 Supra cyberpunk 1000HP build plan (2026-06). Display data only.
module.exports = {
  phases: [
    { n: 1, name: 'Buy the Car', goal: 'Clean MK3 Supra chassis', items: [
      { item: 'Clean MK3 Supra', cost: '$8k–$20k', install: '—' },
      { item: 'Registration/title/tax', cost: '$500–$2k', install: '—' },
    ], totals: { running: '$8.5k–$22k' } },
    { n: 2, name: 'Reliability', goal: 'Keep stock engine for now', items: [
      { item: 'Full fluid service', cost: '$200–$500', install: '$150–$400' },
      { item: 'Timing belt/water pump', cost: '$300–$700', install: '$500–$1k' },
      { item: 'Aluminum radiator', cost: '$250–$500', install: '$150–$400' },
      { item: 'Brakes + rotors', cost: '$400–$1k', install: '$300–$700' },
      { item: 'Bushings/wheel bearings', cost: '$400–$1.2k', install: '$500–$1.5k' },
      { item: 'Coilovers (temporary)', cost: '$800–$2k', install: '$300–$700' },
      { item: 'Wheels + tires', cost: '$2k–$5k', install: '$100–$300' },
    ], totals: { parts: '$4.3k–$10.9k', install: '$2k–$5k' } },
    { n: 3, name: 'Cyberpunk Lighting', items: [
      { item: 'RGB halos', cost: '$150–$400', install: '$200–$500' },
      { item: 'RGB demon eyes', cost: '$100–$300', install: '$200–$500' },
      { item: 'RGB controller/app setup', cost: '$50–$150', install: 'Included' },
      { item: 'Pink underglow kit', cost: '$100–$300', install: '$150–$500' },
      { item: 'Interior ambient lighting', cost: '$100–$500', install: '$200–$800' },
      { item: 'Smoked tails/headlights', cost: '$100–$400', install: '$50–$200' },
    ], totals: { parts: '$600–$2k', install: '$600–$2.5k' } },
    { n: 4, name: 'Air Suspension', items: [
      { item: 'Air Lift Performance kit', cost: '$3k–$5k', install: '$1k–$2.5k' },
      { item: 'AccuAir management', cost: '$1.5k–$3k', install: 'Included' },
      { item: 'Compressors/tank/lines', cost: '$800–$2k', install: '$500–$1.5k' },
    ], totals: { parts: '$5.3k–$10k', install: '$1.5k–$4k' } },
    { n: 5, name: 'Power Support Mods', items: [
      { item: 'Big brake kit', cost: '$2k–$6k', install: '$300–$800' },
      { item: 'Fuel system', cost: '$1.5k–$4k', install: '$800–$2k' },
      { item: 'Oil cooler', cost: '$300–$800', install: '$200–$600' },
      { item: 'Electric fans', cost: '$200–$500', install: '$100–$300' },
      { item: 'Differential upgrade', cost: '$1k–$3k', install: '$500–$1.5k' },
    ], totals: { parts: '$5k–$14k', install: '$2k–$5k' } },
    { n: 6, name: 'Buy Complete 2JZ Swap', items: [
      { item: '2JZ-GTE engine', cost: '$5k–$12k', install: '—' },
      { item: 'Transmission (CD009/T56/TH400)', cost: '$2k–$8k', install: '—' },
      { item: 'Swap harness/ECU', cost: '$2k–$5k', install: '—' },
      { item: 'Swap mounts/driveshaft', cost: '$1k–$3k', install: '—' },
    ], totals: { parts: '$10k–$28k' } },
    { n: 7, name: 'Engine Swap + Big Turbo', items: [
      { item: 'Single turbo kit', cost: '$4k–$10k', install: '$1k–$3k' },
      { item: 'Intercooler setup', cost: '$800–$2k', install: '$300–$1k' },
      { item: 'Exhaust', cost: '$1k–$3k', install: '$300–$800' },
      { item: 'Standalone ECU tune', cost: '$1k–$3k', install: '$1k–$2k' },
      { item: 'Swap labor', cost: '—', install: '$5k–$15k' },
    ], totals: { parts: '$6.8k–$18k', install: '$7.6k–$21k' } },
    { n: 8, name: 'Widebody + Final Look', items: [
      { item: 'Widebody kit', cost: '$2k–$8k', install: '$2k–$8k' },
      { item: 'Paint/wrap', cost: '$4k–$15k', install: 'Included' },
      { item: 'Splitter/diffuser', cost: '$500–$3k', install: '$300–$1k' },
      { item: 'Final wheels/fitment', cost: '$2k–$6k', install: '$100–$300' },
    ], totals: { parts: '$8.5k–$32k', install: '$2.4k–$9k' } },
    { n: 9, name: 'True 1000HP Build', items: [
      { item: 'Forged internals', cost: '$4k–$10k', install: '$3k–$8k' },
      { item: 'Bigger turbo', cost: '$2k–$5k', install: '$500–$1.5k' },
      { item: 'E85 conversion', cost: '$500–$2k', install: '$300–$800' },
      { item: 'Dyno tuning', cost: '$800–$2k', install: 'Included' },
    ], totals: { parts: '$7.3k–$19k', install: '$3.8k–$10k' } },
  ],
  finals: [
    { level: 'DIY-heavy build', total: '$40k–$60k' },
    { level: 'Balanced realistic build', total: '$60k–$90k' },
    { level: 'High-end professional show build', total: '$100k–$150k+' },
  ],
  note: 'Tracker donor budget is set to $1k–$9k for the Phase-1 chassis (scored, never filtered).',
};
```

- [ ] **Step 4: Wire into src/api.js**

Add requires at top:

```js
const { scoreDonor } = require('./score');
const buildPlan = require('./build-plan');
```

In the `/api/listings` handler, replace `listings: store.queryListings(),` with:

```js
      listings: store.queryListings().map((l) => {
        const d = scoreDonor(l);
        return { ...l, donor_score: d.score, donor_tier: d.tier, donor_reasons: d.reasons };
      }),
```

Add a route after the tier2 route:

```js
  app.get('/api/plan', (_req, res) => res.json(buildPlan));
```

- [ ] **Step 5: Run to verify it passes**

Run: `node --test test/api.test.js`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add supra-tracker/src/build-plan.js supra-tracker/src/api.js supra-tracker/test/api.test.js
git commit -m "supra-tracker: donor fields in api + build plan endpoint"
```

---

### Task 5: Dashboard donor mode + Build Plan page + deploy

**Files:**
- Modify: `supra-tracker/public/index.html`, `supra-tracker/public/app.js`, `supra-tracker/public/style.css`
- Create: `supra-tracker/public/build-plan.html`

- [ ] **Step 1: index.html — donor toggle, sort option, header link**

In the header `<h1>` line, change the sub span to include the link:

```html
  <h1>🏁 Supra Tracker <span class="sub">A70 Turbo hunt · home base Mesa, AZ · <a class="planlink" href="build-plan.html">Build Plan →</a></span></h1>
```

In the sort select, add after the `closest` option:

```html
    <option value="donor">best donor</option>
```

After the `❤️ only` label add:

```html
  <label class="chk donor"><input type="checkbox" id="f-donor"> 🔧 Donor mode</label>
```

- [ ] **Step 2: app.js — donor mode behavior**

a) In `visible()`, read the toggle at the top:

```js
  const donorMode = $('#f-donor').checked;
```

and change the turbo filter lines to respect it:

```js
    if (!donorMode) {
      if (fTurbo === 'default' && l.turbo_status === 'non_turbo') return false;
      if (fTurbo === 'confirmed' && l.turbo_status !== 'confirmed') return false;
    }
```

b) In the sort block add a branch before the newest fallback:

```js
  else if (sort === 'donor' || (donorMode && sort === 'newest')) rows.sort((a, b) => b.donor_score - a.donor_score);
```

(the parenthesized clause makes Donor mode default to best-donor ordering while the user hasn't picked another sort)

c) In `cardHtml(l)`, add at the top:

```js
  const donorMode = $('#f-donor').checked;
  const tierColor = { great: 'var(--green)', possible: 'var(--accent)', poor: 'var(--red)' }[l.donor_tier];
  const donorChip = donorMode
    ? `<span class="badge donor" style="border-color:${tierColor};color:${tierColor}">🔧 ${l.donor_score}</span>`
    : '';
  const donorReasons = donorMode
    ? `<div class="meta reasons">${l.donor_reasons.slice(0, 3).map((r) =>
        `<span>${r.delta > 0 ? '+' : ''}${r.delta} ${esc(r.text)}</span>`).join('<br>')}</div>`
    : '';
```

Add `${donorChip}` as the FIRST entry of the `badges` array, and `${donorReasons}` right after the `found ${ago(...)}` meta line in the returned HTML.

d) Grey-out the turbo select while donor mode is on — in `render()` add at the top:

```js
  $('#f-turbo').disabled = $('#f-donor').checked;
```

- [ ] **Step 3: style.css additions**

```css
.planlink { color: var(--new); text-decoration: none; }
.planlink:hover { color: var(--accent); }
.badge.donor { font-weight: 700; }
.reasons span { display: inline; }
#filters label.donor { color: var(--accent); font-weight: 600; }
#filters select:disabled { opacity: 0.4; }
```

- [ ] **Step 4: public/build-plan.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MK3 Cyberpunk 1000HP — Build Plan</title>
<link rel="stylesheet" href="style.css">
<style>
  .wrap { max-width: 860px; margin: 0 auto; padding: 24px 20px; }
  .back { color: var(--new); }
  .wrap h1 { margin: 10px 0 4px; } .wrap .sub { color: var(--dim); font-size: 13px; }
  .donors { display: grid; gap: 8px; margin: 16px 0 24px; }
  .donor-row { display: flex; gap: 10px; align-items: center; background: var(--panel);
    border: 1px solid var(--line); border-radius: 8px; padding: 8px 12px; font-size: 14px; }
  .donor-row .score { font-weight: 800; min-width: 52px; }
  .donor-row a { color: var(--text); text-decoration: none; font-weight: 600; flex: 1; }
  .donor-row a:hover { color: var(--accent); }
  .donor-row .meta2 { color: var(--dim); font-size: 12.5px; }
  .phase { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
    padding: 14px 16px; margin: 14px 0; }
  .phase h2 { font-size: 16px; color: var(--accent); } .phase .goal { color: var(--dim); font-size: 13px; }
  table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13.5px; }
  th, td { text-align: left; padding: 5px 8px; border-bottom: 1px dashed var(--line); }
  th { color: var(--dim); font-weight: 600; font-size: 12px; text-transform: uppercase; }
  td:nth-child(2), td:nth-child(3), th:nth-child(2), th:nth-child(3) { text-align: right; white-space: nowrap; }
  .totals { margin-top: 8px; color: var(--dim); font-size: 13px; }
  .totals b { color: var(--text); }
  .finals { margin: 20px 0; }
  .finals td { font-size: 15px; } .finals td:last-child { color: var(--accent); font-weight: 700; }
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="/">← back to dashboard</a>
  <h1>🔧 MK3 Supra Cyberpunk 1000HP Build</h1>
  <div class="sub">Phase-1 donor budget on the tracker: $1k–$9k (scored, never filtered)</div>

  <h2 style="margin-top:18px">Top donor candidates right now</h2>
  <div class="donors" id="donors">loading…</div>

  <div id="phases"></div>
  <div class="finals phase">
    <h2>Final estimate</h2>
    <table id="finals"></table>
  </div>
</div>
<script>
const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
(async () => {
  const [lRes, pRes] = await Promise.all([fetch('/api/listings'), fetch('/api/plan')]);
  const data = await lRes.json();
  const plan = await pRes.json();

  const top = data.listings
    .filter((l) => l.status === 'active' && !l.hidden)
    .sort((a, b) => b.donor_score - a.donor_score)
    .slice(0, 5);
  const tierColor = { great: 'var(--green)', possible: 'var(--accent)', poor: 'var(--red)' };
  document.getElementById('donors').innerHTML = top.map((l) => `
    <div class="donor-row">
      <span class="score" style="color:${tierColor[l.donor_tier]}">🔧 ${l.donor_score}</span>
      <a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.title)}</a>
      <span class="meta2">${l.price != null ? '$' + l.price.toLocaleString() : 'no price'}
        · ${l.distance_mi != null ? Math.round(l.distance_mi) + ' mi' : '? mi'}</span>
    </div>`).join('') || '<div class="donor-row">no active listings yet</div>';

  document.getElementById('phases').innerHTML = plan.phases.map((ph) => `
    <div class="phase">
      <h2>Phase ${ph.n} — ${esc(ph.name)}</h2>
      ${ph.goal ? `<div class="goal">${esc(ph.goal)}</div>` : ''}
      <table>
        <tr><th>Part</th><th>Cost</th><th>Install</th></tr>
        ${ph.items.map((it) => `<tr><td>${esc(it.item)}</td><td>${esc(it.cost)}</td><td>${esc(it.install)}</td></tr>`).join('')}
      </table>
      <div class="totals">${Object.entries(ph.totals).map(([k, v]) => `${k}: <b>${esc(v)}</b>`).join(' · ')}</div>
    </div>`).join('');

  document.getElementById('finals').innerHTML =
    plan.finals.map((f) => `<tr><td>${esc(f.level)}</td><td>${esc(f.total)}</td></tr>`).join('');
})();
</script>
</body>
</html>
```

- [ ] **Step 5: Full suite + browser verification**

Run: `npm test` → ALL tests pass.

Restart the deployed tracker so it serves the new code, then verify in the browser (preview or直接):

```powershell
Stop-ScheduledTask -TaskName SupraTracker; Start-Sleep 2; Start-ScheduledTask -TaskName SupraTracker
```

Checks at http://localhost:3070:
1. Donor mode OFF: dashboard identical to before (no chips, turbo filter enabled).
2. Donor mode ON: score chips + reasons appear, list reorders best-donor-first, turbo select greys out, non-turbo cars appear.
3. The $46k Oceanside car shows 🔴 with "way over budget for a donor"; cheap AZ cars near the top.
4. `build-plan.html`: top-5 donors render with live scores; all 9 phases + finals tables render.
5. No browser console errors.

- [ ] **Step 6: Commit**

```bash
git add supra-tracker/public/
git commit -m "supra-tracker: donor mode ui + build plan page"
```

---

## Plan self-review (done at write time)

- **Spec coverage:** score rules incl. price bands/rust precedence/caps (Task 1), allow-all + config (Task 1), description migration + CC/Hemmings store-through (Task 2), enrichment + turbo reclassify + scheduler wiring + sentinel (Task 3), API donor fields + /api/plan + build-plan data (Task 4), donor toggle UI behavior + chips + reasons + sort + plan page + deploy restart (Task 5). Success criteria 1–4 verified in Task 5 Step 5.
- **Placeholders:** none; every code step shows the code. Fixture URLs are read from the live db by command (can't be pre-known).
- **Type consistency:** `scoreDonor(l) -> {score, tier, reasons[{delta,text}]}` used identically in api.js and both UIs; store methods `setDescription(id, text)` / `listNeedingDescription(limit)` match enrich.js calls; `DONOR` config keys match score.js usage.
