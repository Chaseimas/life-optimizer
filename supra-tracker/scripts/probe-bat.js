// Dev probe: inspect the BaT Supra model page fixture's embedded data.
const fs = require('fs');

const h = fs.readFileSync('test/fixtures/bat-supra.html', 'utf8');
console.log('bytes:', h.length);
for (const m of h.matchAll(/var\s+(\w+)\s*=/g)) console.log('var:', m[1]);
console.log('class="listing-card count:', (h.match(/class="listing-card/g) || []).length);
console.log('data-listing attrs:', (h.match(/data-listing=/g) || []).length);
console.log('auctions-item-extended:', (h.match(/auctions-item/g) || []).length);
// Show context around the first listings-ish var
for (const name of ['auctionsCurrentInitialData', 'BAT_MODEL_LISTINGS_TOOLBAR', 'listingsData']) {
  const i = h.indexOf(name);
  if (i >= 0) console.log(`\n=== ${name} @${i}:\n`, JSON.stringify(h.slice(i, i + 400)));
}
