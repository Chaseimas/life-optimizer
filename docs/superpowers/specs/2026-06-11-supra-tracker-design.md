# Supra Tracker — Design Spec

**Date:** 2026-06-11
**User:** Kase (Mesa, AZ). Hunting an A70 (MK3) Toyota Supra Turbo, 1991 preferred, willing to drive far. Non-technical user; app must run itself.

## Goal

A background app on Kase's Windows PC that continuously scans car-listing sites nationwide for A70 Supras, stores everything in a local database, and serves a dashboard at `http://localhost:3070`. No notifications — the dashboard highlights what's new since the last visit.

## Decisions already made (with user)

| Decision | Choice |
|---|---|
| Alerts | None — dashboard only, NEW badges since last visit |
| Hosting | Local PC, free, auto-starts with Windows |
| Architecture | All-in-one Node.js app (matches orb-signal: Node + better-sqlite3) |
| Facebook Marketplace | NOT auto-scraped (login wall, bot detection, ToS). Dashboard provides pre-built one-click FB searches + guide to enable FB's native saved-search alerts |

## What counts as a match

- **Model years 1986–1992** (US A70 generation; Turbo arrived 1987). Listings with no parseable year but "supra" + MK3/A70/MKIII keywords in text are kept and tagged "year unknown".
- **1993+ (MK4) excluded.** Pre-1986 (MK2) excluded.
- **Turbo classification** from title + description keywords:
  - `turbo confirmed`: "turbo", "7m-gte", "7mgte", "1jz", "twin turbo", "targa turbo", "turbocharged"
  - `non-turbo confirmed`: "non-turbo", "non turbo", "na ", "n/a engine", "7m-ge", "7mge" (word-boundary aware; "na" only as standalone token)
  - `unconfirmed`: neither — shown by default with ⚠️ tag (sellers often omit it)
  - Conflicts (both turbo and non-turbo keywords) resolve to `unconfirmed`.
- JDM imports (1JZ-GTE twin-turbo A70s) count as turbo confirmed.
- **1991 model year** gets a ⭐ badge (preferred year).

## Sources

### Tier 1 — auto-scanned

| Source | Method | Cadence |
|---|---|---|
| Craigslist — Southwest regions (all AZ sites, SoCal, Las Vegas, NM, southern UT) | Region search endpoint (JSON API used by their site, HTML fallback) | Every 30 min |
| Craigslist — all other US regions (~470 total) | Same, throttled sweep | Every 4 h |
| eBay Motors (auction + BIN) | Search-results HTML scrape | Every 1 h |
| Bring a Trailer | Model page HTML (`/toyota/mkiii-supra/`) | Every 2 h |
| Cars & Bids | Plain-HTTP attempt on their search/API | Every 2 h |
| Hemmings | Search HTML/JSON | Every 4 h |
| ClassicCars.com | Search HTML | Every 4 h |
| OfferUp | Public search endpoint, best effort | Every 1 h |

- Any Tier 1 source that turns out to be hard-blocked from plain HTTP (likely candidates: Cars & Bids, OfferUp) is **demoted to Tier 2** (manual link) rather than fought with browser automation. v1 ships with **no Playwright/headless browser** — keeps install small and honest.
- Craigslist dedupe note: cross-posted/nearby results dedupe by CL posting ID.

### Tier 2 — one-click manual links on dashboard

- Facebook Marketplace: pre-built Supra searches (Phoenix metro + Tucson + Las Vegas + SoCal + nationwide-radius variants) + a short illustrated guide page for enabling FB's own new-listing alerts.
- AutoTempest (covers Autotrader, Cars.com, CarGurus dealer listings in one search).
- Copart + IAAI salvage auctions.
- Each Tier 2 card shows "last checked by you" (user taps a button to record it).

## Data model (SQLite, `data/supra.db`)

- `listings`: id (pk), source, source_listing_id (unique per source), url, title, year, price, city, state, lat, lon, distance_mi (from Mesa 33.4152, -111.8315), photo_url, description_snippet, turbo_status (confirmed/non_turbo/unconfirmed), first_seen, last_seen, status (active/gone), favorite (bool), hidden (bool)
- `price_history`: listing_id, price, seen_at — row added whenever price changes; dashboard shows 📉/📈 vs previous price
- `scan_log`: source, started_at, finished_at, ok (bool), listings_found, error_text — powers the status bar
- `meta`: key/value (e.g., `last_dashboard_visit` for NEW badges)

**Gone detection:** listing absent from 2 consecutive successful scans of its source → status `gone`. Kept in DB (builds real market-price history). Gone listings visible under a "Sold/Gone" filter.

**NEW badge:** `first_seen` later than the previous dashboard visit timestamp.

**Distance:** offline geocoding via a bundled US cities/zips lat-lon CSV (no API, no cost); haversine from Mesa. Unresolvable locations show "? mi" and sort last by distance.

## Dashboard (single page, served by the app)

- **Cards:** photo, year, title, price, city/state + miles from Mesa, source badge, first-seen ("2 h ago"), NEW badge, ⭐ 1991, ⚠️ unconfirmed turbo, 📉 price drop.
- **Filters:** max price, max distance, year range, source, turbo status (default: confirmed + unconfirmed shown, non-turbo hidden), show/hide gone listings, favorites only.
- **Sorts:** newest, cheapest, closest.
- **Per-card actions:** ❤️ favorite, 🚫 hide (persisted).
- **Status bar:** per-source last successful scan time, current errors/blocks in plain English ("OfferUp is blocking scans — use the quick link").
- **Tier 2 panel:** the manual-check links + FB alert guide.
- Clean, fast, no framework needed beyond vanilla JS or a tiny lib; styling is dark, readable, phone-friendly layout not required (PC-only per user).

## Architecture

- **One Node.js process** (`node server.js`): Express serves dashboard + JSON API; in-process scheduler (node-cron) runs scans.
- **Each source = one scraper module** with a common interface: `scrape() → Listing[]`. Failures isolated per source; one site breaking never affects others.
- **Politeness:** ~1 request per 2 s per host with jitter, normal desktop-browser User-Agent, gzip. Per-source circuit breaker: 3 consecutive failures → exponential backoff (max 24 h) + dashboard status note.
- **Auto-start:** setup script registers a Windows Task Scheduler logon task. Also `npm start` for manual runs and `npm run scan -- --once <source>` for testing.
- **Stack:** Node 18+, express, better-sqlite3, cheerio, node-cron. No headless browser in v1.

## Testing

- Parser unit tests against saved HTML/JSON fixtures per source (`node:test`, zero extra deps) — catches site redesigns fast.
- Match/classification tests: year extraction, turbo keyword rules, MK4 exclusion.
- `--once` end-to-end scan mode for manual verification.

## Out of scope (v1)

- Facebook/OfferUp/dealer-site browser automation, headless browsers
- Push/email notifications
- Cloud hosting
- Cross-source duplicate merging (same car on CL + FB)
- VIN decoding, auction bid tracking, price-prediction

## Success criteria

1. Within one scan cycle, dashboard shows real current A70 listings from at least 4 Tier 1 sources with correct year/price/location/distance.
2. New listings appear automatically and carry NEW badges on next visit.
3. A source being blocked shows a plain-English status note and never crashes the app.
4. Survives a reboot: app auto-starts and keeps scanning without user action.
