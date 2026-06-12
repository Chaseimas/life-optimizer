// Dev tool: show description-fill status per source.
const { getDb } = require('../src/db');

const rows = getDb().prepare(`
  SELECT source, COUNT(*) n,
         SUM(description IS NOT NULL) tried,
         SUM(description IS NOT NULL AND description != '') filled
  FROM listings GROUP BY source`).all();
console.table(rows);
