# Supra Tracker

Hunts 1986–1992 (A70 / MK3) Toyota Supra Turbos around the clock and shows them
on a dashboard: **http://localhost:3070**

| Source | Coverage |
|---|---|
| Craigslist | Southwest (AZ/SoCal/NV/NM/UT/El Paso) every 30 min + all ~420 US regions every 4 h |
| OfferUp | every hour (geo-biased toward Phoenix — great for local deals) |
| Bring a Trailer | live auctions every 2 h |
| ClassicCars.com | every 4 h |
| eBay / Cars & Bids / Hemmings | tried politely; these block robots — after 5 straight blocks they turn into one-click manual links on the dashboard |
| Facebook Marketplace, AutoTempest (dealers), Copart/IAAI | manual one-click links + guide to enable Facebook's own alerts |

## First-time setup

    cd supra-tracker
    npm install
    npm run setup        # downloads geocoding data + craigslist region list
    npm start            # dashboard at http://localhost:3070

Auto-start with Windows (run once, in PowerShell):

    powershell -ExecutionPolicy Bypass -File scripts\install-autostart.ps1
    Start-ScheduledTask -TaskName SupraTracker

## Daily use

Open http://localhost:3070. Blue **NEW** badge = appeared since your last visit.
⭐ = 1991 (preferred year). 📉 = price dropped. ⚠️ = seller didn't say turbo or not —
worth asking. ❤️ to shortlist, 🚫 to dismiss. Sellers that vanish get marked GONE
but stay in the database, so over time you'll see what these actually sell for.

Facebook Marketplace can't be auto-scanned — use the right-hand panel's one-click
searches and set up FB's own alerts (guide linked on the dashboard). That combo
covers the gap properly.

## Commands

    npm start                    # run server + scanners
    npm run scan                 # scan all sources once and exit
    npm run scan -- ebay         # scan one source (keys: craigslist-sw, craigslist-us,
                                 #   offerup, ebay, bat, carsandbids, hemmings, classiccars)
    npm test                     # run test suite (32 tests)

## When a site changes its layout

The status panel shows the source erroring in red. Fix = update that one parser in
`src/scrapers/<source>.js` against a fresh capture (`node scripts/fetch-fixture.js <url> <file>`,
fixtures live in `test/fixtures/`). Each source is isolated — one breaking never
affects the others.

If you ever want full eBay coverage despite the bot wall: eBay's official Browse API
is free (developer.ebay.com, 5000 calls/day) — that would be a small upgrade to
`src/scrapers/ebay.js`.
