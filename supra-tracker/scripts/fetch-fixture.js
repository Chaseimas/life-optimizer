// Dev tool: fetch a URL with the app's politeFetch and save to a fixture file.
//   node scripts/fetch-fixture.js <url> <outfile>
const fs = require('fs');
const { politeFetch } = require('../src/http');

(async () => {
  const [url, out] = process.argv.slice(2);
  const res = await politeFetch(url);
  const body = await res.text();
  fs.writeFileSync(out, body);
  console.log(`HTTP ${res.status} | ${body.length} bytes -> ${out}`);
})().catch((e) => { console.error('FETCH FAILED:', e.message); process.exit(1); });
