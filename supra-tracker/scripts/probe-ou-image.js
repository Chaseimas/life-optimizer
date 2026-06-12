// Dev probe: what does the OfferUp listing `image` field actually look like?
const fs = require('fs');
const cheerio = require('cheerio');

const html = fs.readFileSync('test/fixtures/offerup-supra.html', 'utf8');
const raw = cheerio.load(html)('#__NEXT_DATA__').text();
const data = JSON.parse(raw);
let shown = 0;
(function walk(node) {
  if (!node || typeof node !== 'object' || shown >= 3) return;
  if (Array.isArray(node)) return node.forEach(walk);
  if ((node.listingId || node.id) && node.title && node.price !== undefined) {
    shown++;
    console.log('title:', node.title);
    console.log('  image:', JSON.stringify(node.image));
    console.log('  photos:', JSON.stringify(node.photos ? node.photos[0] : undefined));
    console.log('  keys:', Object.keys(node).join(','));
  }
  Object.values(node).forEach(walk);
})(data);
