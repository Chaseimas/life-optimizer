# Supra Tracker: Donor Mode + Build Plan Page — Design Spec

**Date:** 2026-06-12
**Builds on:** `docs/superpowers/specs/2026-06-11-supra-tracker-design.md` (tracker is built, deployed, running as Windows task)

## Goal

Score every tracked A70 listing for fitness as a **2JZ-swap donor chassis** for Kase's 1000HP cyberpunk build, surface the score + reasons on the dashboard behind a Donor Mode toggle, and add a read-only Build Plan reference page with his 9 phases and a live "top donor candidates" strip.

## Decisions made with user

| Decision | Choice |
|---|---|
| Donor logic | Chassis is king: non-turbo and not-running cars are GOOD candidates (engine gets replaced by 2JZ-GTE) |
| Phase-1 chassis budget | **$1,000–$9,000**, but never filter anything out — score only ("allow all") |
| Rust | Location-aware: structural-area rust is heavily penalized; cosmetic surface rust barely matters |
| Build plan page | Read-only reference (no purchase check-off tracking) |
| Ad-text source | Enrich new Craigslist/OfferUp listings with one polite detail-page fetch to get full ad text |

## Donor Score (`src/score.js`)

Pure function: `scoreDonor({ title, snippet, description, price, state, turbo_status }) -> { score, tier, reasons }`
- Text = title + snippet + description (whatever exists), lowercased.
- Start at 50, apply deltas, clamp 0–100.
- `reasons` = array of `{ delta, text }` for every rule that fired (UI shows top ones).
- Tiers: `great` ≥ 70 · `possible` 50–69 · `poor` < 50.

### Price vs budget ($1k–$9k)

| Price | Delta | Reason text |
|---|---|---|
| $1,000–$9,000 | +20 | in Phase-1 budget |
| < $1,000 | +5 | suspiciously cheap — verify it's real |
| $9,001–$12,000 | +6 | slightly over budget |
| $12,001–$18,000 | −8 | over budget |
| > $18,000 | −20 | way over budget for a donor |
| null | −5 | no price listed |

### Rust (location-aware; all matching rules apply, positives don't suppress negatives)

- Positive: `rust free`, `rust-free`, `no rust`, `zero rust`, `no rot`, `solid floors`, `solid frame`, `solid underneath` → **+15** (apply once)
- Structural: rust/rot within ~40 chars of `frame`, `rail(s)`, `rocker(s)`, `floor(s)`, `pan(s)`, `strut`, `tower(s)`, `quarter(s)`, `arch(es)`, `hatch`, `underneath`, `undercarriage` (either word order) → **−25** "structural rust mentioned" (apply once)
- Cosmetic qualifier: `surface rust`, `minor rust`, `light rust`, `little rust`, `rust bubble(s)`, `bubbling` → **−6** "cosmetic rust only" (apply once, and suppresses the generic rule below)
- Generic: any other `rust`/`rusty`/`rusted`/`rot` mention not already counted as positive/cosmetic → **−12** "rust mentioned" (apply once; skipped if structural already fired)

### Title status

- `clean title` → +10
- `salvage`, `rebuilt title`, `branded title`, `no title`, `bill of sale` → −15

### Condition positives (each +5, capped at +10 total)

`garage kept`/`garaged`, `original paint`, `straight body`, `one owner`/`1 owner`, `adult owned`, `always covered`, `all stock`/`bone stock`

### Swap-friendly chassis deals

Dead-engine signals: `needs engine`, `no engine`, `engine out`, `no motor`, `blown`, `bad engine`, `knock`, `doesn't run`, `does not run`, `not running`, `won't start`, `wont start`, `roller`
- Dead engine AND price ≤ $6,000 → **+12** "donor deal: cheap chassis, engine's getting swapped anyway"
- Dead engine AND price > $9,000 → **−8** "not running but priced like a runner"
- Dead engine otherwise (incl. no price) → **+4** "engine condition irrelevant for swap"
- `parts car` / `parting out` → **−15** (usually stripped/no title)

### Other

- Frame/accident: `frame damage`, `frame rot`, `bent frame`, `wrecked`, `accident`, `front end damage` → −15
- Dry state (AZ, NM, NV, CA, TX, UT, CO) → +6 "dry-climate car"
- `turbo_status === 'non_turbo'` → +4 "non-turbo = cheaper chassis, engine's going anyway"

Config: budget window + dry states + dead-engine price thresholds live in `src/config.js` (`DONOR`).

## Description enrichment (`src/enrich.js`)

After each scan cycle, for up to **10** listings per cycle where `description IS NULL` and source is `craigslist` or `offerup`:
- Craigslist: politeFetch listing URL, extract `#postingbody` text (strip the "QR Code Link to This Post" boilerplate).
- OfferUp: politeFetch listing URL, parse `__NEXT_DATA__`, walk for the listing's `description` string.
- Store trimmed text (cap 4000 chars). On any failure store `''` (sentinel: tried, unavailable — never retried). Other sources keep `NULL` (ClassicCars/Hemmings already provide snippets; BaT/eBay skipped in v1).
- After storing a non-empty description, **re-classify turbo_status** from title+description (full text often reveals turbo/non-turbo) and update the row.
- Wire-up: scheduler calls `enrichBatch(store)` after each `runEntry` completes; scan-once script calls it too.

## Schema migration

`listings` gains `description TEXT` (nullable). In `db.js`: after `exec(SCHEMA)`, run `ALTER TABLE listings ADD COLUMN description TEXT` inside try/catch (no-op when column exists). New-listing inserts leave it NULL; ClassicCars/Hemmings store their JSON-LD description into `description` at insert (they already have it — snippet stays the 300-char display cut).

## API

- `/api/listings`: each listing row gains `donor_score` (int), `donor_tier` (`great|possible|poor`), `donor_reasons` (array, sorted by |delta| desc) — computed live in `api.js` via `score.js` (nothing stored; weight tweaks apply instantly).
- `/api/plan`: returns the build plan JSON from `src/build-plan.js` (phases, items, cost ranges, totals) — consumed by the plan page.

## UI

**Dashboard (`public/`):**
- 🔧 **Donor mode** checkbox in the filter bar. ON ⇒ turbo filter forced to "show everything" (control disabled while on), sort switches to new option "best donor", each card shows a colored score chip (🟢 72 / 🟡 55 / 🔴 31) + top 3 reasons as a small list. OFF ⇒ exactly today's behavior, no donor UI anywhere.
- Sort dropdown gains "best donor" (usable outside donor mode too).
- Header gains link: `Build Plan →` (to `build-plan.html`).

**Build Plan page (`public/build-plan.html` + small inline JS):**
- Top strip: **Top donor candidates right now** — top 5 active listings by donor score from `/api/listings` (title, price, score chip, distance, link).
- Below: the 9 phases as tables (item / cost / install), phase totals, and the final estimate table (DIY $40–60k · balanced $60–90k · show build $100–150k+) — exact figures from Kase's plan, hardcoded in `src/build-plan.js`.
- Same dark styling (`style.css` + small page-specific styles).

## Testing

- `score.js`: unit tests per rule group — budget bands, structural vs cosmetic vs generic rust precedence, positive+structural combination ("no rust except rockers" nets both), donor-deal price gates, caps, clamping, tier mapping.
- `enrich.js`: parser tests against fixtures — live-captured CL posting page and OfferUp item page; failure → `''` sentinel; turbo_status upgrade from body text.
- `db.js`: migration test — db created with old schema gets `description` column on reopen.
- API test: listings response includes `donor_score`/`donor_tier`/`donor_reasons`; `/api/plan` returns 9 phases.

## Out of scope

- Purchase check-off / spend tracking (declined)
- LLM/photo-based condition analysis
- Enrichment for BaT/eBay/Hemmings detail pages
- Storing scores in the DB

## Success criteria

1. Donor mode ON: every card shows a score chip + reasons; sort "best donor" puts an in-budget rust-free car above the $46k collector car (which shows 🔴).
2. A new CL/OfferUp listing gets its full ad text within one scan cycle and its score reflects body keywords.
3. Build Plan page renders all 9 phases + totals and live top-5 donors.
4. Donor mode OFF leaves the dashboard exactly as it is today.
