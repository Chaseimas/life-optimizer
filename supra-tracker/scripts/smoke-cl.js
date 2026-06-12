// Dev smoke test: live-scrape a few craigslist regions and show what the matcher keeps.
const cl = require('../src/scrapers/craigslist');
const { evaluateCandidate } = require('../src/match');

(async () => {
  const regions = process.argv.slice(2);
  const names = regions.length ? regions : ['phoenix', 'losangeles', 'sandiego'];
  const r = await cl.scrapeRegions(names);
  console.log(`covered: ${r.coveredRegions.join(', ')}`);
  console.log(`raw candidates: ${r.candidates.length}`);
  const kept = r.candidates.filter((c) => evaluateCandidate(c).accept);
  console.log(`kept after matching: ${kept.length}`);
  for (const c of kept.slice(0, 8)) {
    const ev = evaluateCandidate(c);
    console.log(`- [${ev.year ?? '??'}|${ev.turboStatus}] ${c.title} | $${c.price ?? '?'} | ${c.city ?? '?'}, ${c.state ?? '?'} | ${c.url}`);
  }
})().catch((e) => { console.error('SMOKE FAILED:', e); process.exit(1); });
