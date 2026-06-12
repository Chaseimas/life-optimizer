// Dev probe: live-test the best-effort scrapers. Both OK and blocked are
// designed-for outcomes; this just reports which one we got today.
(async () => {
  for (const name of ['carsandbids', 'offerup']) {
    try {
      const r = await require(`../src/scrapers/${name}`).scrape();
      console.log(`${name}: OK, ${r.candidates.length} items`);
      for (const c of r.candidates.slice(0, 3)) console.log(`  - ${c.title} | $${c.price ?? '?'} | ${c.url}`);
    } catch (e) {
      console.log(`${name}: FAILED: ${e.message} (blocked=${!!e.blocked})`);
    }
  }
})();
