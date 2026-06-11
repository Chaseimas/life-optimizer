const path = require('path');

module.exports = {
  PORT: 3070,
  HOME: { lat: 33.4152, lon: -111.8315, label: 'Mesa, AZ' },
  DATA_DIR: path.join(__dirname, '..', 'data'),
  PUBLIC_DIR: path.join(__dirname, '..', 'public'),
  USER_AGENT:
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
  MIN_YEAR: 1986,
  MAX_YEAR: 1992,
  PREFERRED_YEAR: 1991,
  // Craigslist regions scanned every 30 min (AZ + SoCal + NV + NM + UT + El Paso)
  SW_REGIONS: [
    'phoenix', 'tucson', 'flagstaff', 'mohave', 'prescott', 'showlow',
    'sierravista', 'yuma', 'losangeles', 'orangecounty', 'sandiego',
    'inlandempire', 'palmsprings', 'imperial', 'bakersfield', 'lasvegas',
    'albuquerque', 'santafe', 'lascruces', 'farmington', 'roswell',
    'stgeorge', 'saltlakecity', 'provo', 'ogden', 'elpaso',
  ],
  // Tier 2: manual one-click searches shown on the dashboard
  TIER2_LINKS: [
    {
      key: 'fb-phoenix',
      label: 'Facebook Marketplace — Phoenix metro',
      url: 'https://www.facebook.com/marketplace/phoenix/search?query=toyota%20supra&minYear=1986&maxYear=1992',
    },
    {
      key: 'fb-tucson',
      label: 'Facebook Marketplace — Tucson',
      url: 'https://www.facebook.com/marketplace/tucson/search?query=toyota%20supra&minYear=1986&maxYear=1992',
    },
    {
      key: 'fb-vegas',
      label: 'Facebook Marketplace — Las Vegas',
      url: 'https://www.facebook.com/marketplace/lasvegas/search?query=toyota%20supra&minYear=1986&maxYear=1992',
    },
    {
      key: 'fb-la',
      label: 'Facebook Marketplace — Los Angeles',
      url: 'https://www.facebook.com/marketplace/la/search?query=toyota%20supra&minYear=1986&maxYear=1992',
    },
    {
      key: 'autotempest',
      label: 'AutoTempest (Autotrader + Cars.com + CarGurus dealers)',
      url: 'https://www.autotempest.com/results?make=toyota&model=supra&minyear=1986&maxyear=1992&zip=85201&radius=any',
    },
    {
      key: 'copart',
      label: 'Copart salvage auctions',
      url: 'https://www.copart.com/lotSearchResults/?free=true&query=toyota%20supra',
    },
    {
      key: 'iaai',
      label: 'IAAI salvage auctions',
      url: 'https://www.iaai.com/Search?Keyword=toyota%20supra',
    },
  ],
};
