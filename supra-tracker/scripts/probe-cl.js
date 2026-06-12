// Dev probe: inspect what Craigslist serves no-JS clients (run during scraper development).
const fs = require('fs');

const file = process.argv[2];
const h = fs.readFileSync(file, 'utf8');
console.log('bytes:', h.length);
console.log('has <ol class="cl-static-search-results">:', h.includes('cl-static-search-results"'));
const lis = h.match(/<li class="cl-static-search-result"/g) || [];
console.log('li.cl-static-search-result count:', lis.length);
const i = h.indexOf('<li class="cl-static-search-result"');
if (i >= 0) console.log('sample:', JSON.stringify(h.slice(i, i + 600)));
