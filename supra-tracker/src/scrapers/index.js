const craigslist = require('./craigslist');
const ebay = require('./ebay');
const bat = require('./bat');
const hemmings = require('./hemmings');
const classiccars = require('./classiccars');
const carsandbids = require('./carsandbids');
const offerup = require('./offerup');

// key: unique schedule entry. source: the listings.source value (craigslist has
// two entries feeding one source). demotable sources hard-block bots from time
// to time; after 5 straight blocked errors the scheduler retires them to the
// dashboard's manual-links panel (manualUrl).
const SOURCES = [
  { key: 'craigslist-sw', source: 'craigslist', label: 'Craigslist (Southwest)', cadenceMin: 30,
    run: () => craigslist.scrapeRegions(craigslist.swRegions()) },
  { key: 'craigslist-us', source: 'craigslist', label: 'Craigslist (Nationwide)', cadenceMin: 240,
    run: () => craigslist.scrapeRegions(craigslist.allRegionNames()) },
  { key: 'offerup', source: 'offerup', label: 'OfferUp', cadenceMin: 60,
    run: () => offerup.scrape(), demotable: true, manualUrl: offerup.MANUAL_URL },
  { key: 'ebay', source: 'ebay', label: 'eBay Motors', cadenceMin: 60,
    run: () => ebay.scrape(), demotable: true, manualUrl: ebay.MANUAL_URL },
  { key: 'bat', source: 'bat', label: 'Bring a Trailer', cadenceMin: 120, run: () => bat.scrape() },
  { key: 'carsandbids', source: 'carsandbids', label: 'Cars & Bids', cadenceMin: 120,
    run: () => carsandbids.scrape(), demotable: true, manualUrl: carsandbids.MANUAL_URL },
  { key: 'hemmings', source: 'hemmings', label: 'Hemmings', cadenceMin: 240,
    run: () => hemmings.scrape(), demotable: true, manualUrl: hemmings.MANUAL_URL },
  { key: 'classiccars', source: 'classiccars', label: 'ClassicCars.com', cadenceMin: 240,
    run: () => classiccars.scrape() },
];

module.exports = { SOURCES };
