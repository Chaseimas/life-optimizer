const fs = require('fs');
const path = require('path');
const config = require('./config');

const R_MI = 3958.8;
function haversineMiles(lat1, lon1, lat2, lon2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R_MI * Math.asin(Math.sqrt(a));
}

function normCity(name) {
  return String(name || '')
    .toLowerCase()
    .replace(/\s+(city|town|village|borough|municipality|cdp)$/i, '')
    .replace(/\s+/g, ' ')
    .trim();
}

let places = new Map(); // "az|mesa" -> {lat, lon}

// Gazetteer format drifts year to year (2023 was tab-delimited, 2025 is
// pipe-delimited with an extra GEOIDFQ column) - read the header to locate columns.
function _loadFromText(text) {
  places = new Map();
  const lines = text.split('\n');
  const delim = lines[0].includes('|') ? '|' : '\t';
  const header = lines[0].split(delim).map((h) => h.trim().toUpperCase());
  const iState = header.indexOf('USPS');
  const iName = header.indexOf('NAME');
  const iLat = header.indexOf('INTPTLAT');
  const iLon = header.indexOf('INTPTLONG');
  if (iState < 0 || iName < 0 || iLat < 0 || iLon < 0) return 0;
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(delim);
    if (cols.length <= Math.max(iLat, iLon)) continue;
    const state = cols[iState].trim().toLowerCase();
    const name = normCity(cols[iName]);
    const lat = parseFloat(cols[iLat]);
    const lon = parseFloat(cols[iLon]);
    if (!state || !name || isNaN(lat) || isNaN(lon)) continue;
    const key = `${state}|${name}`;
    if (!places.has(key)) places.set(key, { lat, lon });
  }
  return places.size;
}

function loadGeo() {
  const file = path.join(config.DATA_DIR, 'gazetteer.txt');
  if (!fs.existsSync(file)) {
    console.warn('[geo] gazetteer.txt missing - run `npm run setup`. Distances will show as "?".');
    return 0;
  }
  return _loadFromText(fs.readFileSync(file, 'utf8'));
}

function geocode(city, state) {
  if (!city || !state) return null;
  return places.get(`${String(state).toLowerCase()}|${normCity(city)}`) || null;
}

function distanceFromHome(city, state) {
  const p = geocode(city, state);
  if (!p) return null;
  return Math.round(haversineMiles(config.HOME.lat, config.HOME.lon, p.lat, p.lon));
}

module.exports = { haversineMiles, normCity, _loadFromText, loadGeo, geocode, distanceFromHome };
