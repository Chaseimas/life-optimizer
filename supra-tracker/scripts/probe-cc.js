// Dev probe: inspect the ClassicCars fixture for JSON-LD and card markup.
const fs = require('fs');
const cheerio = require('cheerio');

const h = fs.readFileSync('test/fixtures/classiccars-supra.html', 'utf8');
const $ = cheerio.load(h);
console.log('bytes:', h.length);
$('script[type="application/ld+json"]').each((i, s) => {
  const raw = $(s).text();
  console.log(`\n=== JSON-LD #${i} (${raw.length} chars):`);
  console.log(raw.slice(0, 1200));
});
console.log('\nsearch-result divs:', $('div.search-result').length);
console.log('article tags:', $('article').length);
const cards = h.match(/class="[^"]*(card|listing|result)[^"]*"/g) || [];
console.log('card-ish classes (first 10):', [...new Set(cards)].slice(0, 10));
