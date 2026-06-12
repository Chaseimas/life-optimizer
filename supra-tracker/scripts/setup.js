// One-time setup: downloads the Census places gazetteer (offline geocoding)
// and the Craigslist US region list. Both land in data/.
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const cheerio = require('cheerio');
const config = require('../src/config');

// Census moves this yearly; directory pattern verified 2026-06:
// https://www2.census.gov/geo/docs/maps-data/data/gazetteer/<YEAR>_Gazetteer/<YEAR>_Gaz_place_national.zip
const GAZ_URL =
  'https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_place_national.zip';

const STATE_ABBR = {
  alabama: 'AL', alaska: 'AK', arizona: 'AZ', arkansas: 'AR', california: 'CA',
  colorado: 'CO', connecticut: 'CT', delaware: 'DE', 'district of columbia': 'DC',
  florida: 'FL', georgia: 'GA', hawaii: 'HI', idaho: 'ID', illinois: 'IL',
  indiana: 'IN', iowa: 'IA', kansas: 'KS', kentucky: 'KY', louisiana: 'LA',
  maine: 'ME', maryland: 'MD', massachusetts: 'MA', michigan: 'MI', minnesota: 'MN',
  mississippi: 'MS', missouri: 'MO', montana: 'MT', nebraska: 'NE', nevada: 'NV',
  'new hampshire': 'NH', 'new jersey': 'NJ', 'new mexico': 'NM', 'new york': 'NY',
  'north carolina': 'NC', 'north dakota': 'ND', ohio: 'OH', oklahoma: 'OK',
  oregon: 'OR', pennsylvania: 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
  'south dakota': 'SD', tennessee: 'TN', texas: 'TX', utah: 'UT', vermont: 'VT',
  virginia: 'VA', washington: 'WA', 'west virginia': 'WV', wisconsin: 'WI', wyoming: 'WY',
};

async function downloadGazetteer() {
  const zipPath = path.join(config.DATA_DIR, 'gazetteer.zip');
  const txtPath = path.join(config.DATA_DIR, 'gazetteer.txt');
  if (fs.existsSync(txtPath)) { console.log('[setup] gazetteer.txt already present'); return; }
  console.log('[setup] downloading Census gazetteer...');
  const res = await fetch(GAZ_URL, { headers: { 'User-Agent': config.USER_AGENT } });
  if (!res.ok) throw new Error(`gazetteer download failed: HTTP ${res.status}. Find the current "Places National" file under census.gov Gazetteer Files and update GAZ_URL.`);
  fs.writeFileSync(zipPath, Buffer.from(await res.arrayBuffer()));
  // Windows: use PowerShell to unzip (no extra npm deps)
  execSync(`powershell -NoProfile -Command "Expand-Archive -Force '${zipPath}' '${config.DATA_DIR}'"`);
  const extracted = fs.readdirSync(config.DATA_DIR).find((f) => /gaz_place_national.*\.txt$/i.test(f));
  if (!extracted) throw new Error('unzip produced no Gaz_place_national txt');
  fs.renameSync(path.join(config.DATA_DIR, extracted), txtPath);
  fs.unlinkSync(zipPath);
  console.log('[setup] gazetteer ready');
}

async function downloadClRegions() {
  const outPath = path.join(config.DATA_DIR, 'cl-regions.json');
  if (fs.existsSync(outPath)) { console.log('[setup] cl-regions.json already present'); return; }
  console.log('[setup] downloading Craigslist region list...');
  const res = await fetch('https://www.craigslist.org/about/sites', {
    headers: { 'User-Agent': config.USER_AGENT },
  });
  if (!res.ok) throw new Error(`craigslist sites page: HTTP ${res.status}`);
  const $ = cheerio.load(await res.text());
  const regions = [];
  // Page structure: <h2><a name="US"></a>US</h2> then <div class="colmask"> with
  // states as h4 and regions as li > a (href like https://phoenix.craigslist.org/)
  const usHeader = $('h2')
    .filter((_, el) => $(el).text().trim().toUpperCase() === 'US')
    .first();
  const usSection = usHeader.nextAll('div.colmask').first();
  usSection.find('h4').each((_, h4) => {
    const stateName = $(h4).text().trim().toLowerCase();
    const abbr = STATE_ABBR[stateName];
    if (!abbr) return;
    $(h4).next('ul').find('a').each((_, a) => {
      const href = $(a).attr('href') || '';
      const m = href.match(/^https?:\/\/([a-z0-9]+)\.craigslist\.org/i);
      if (m) regions.push({ region: m[1].toLowerCase(), state: abbr, name: $(a).text().trim() });
    });
  });
  if (regions.length < 300) throw new Error(`only found ${regions.length} regions - selector for about/sites needs updating`);
  fs.writeFileSync(outPath, JSON.stringify(regions, null, 1));
  console.log(`[setup] ${regions.length} craigslist regions saved`);
}

(async () => {
  fs.mkdirSync(config.DATA_DIR, { recursive: true });
  await downloadGazetteer();
  await downloadClRegions();
  console.log('[setup] done');
})().catch((e) => { console.error('[setup] FAILED:', e.message); process.exit(1); });
