/** Emergency flatten: cancel all open orders + close all positions. Verify flat. */
import * as alpaca from "../src/engine-stocks/alpaca";

async function main() {
  const before = await alpaca.getPositions();
  console.log(`Positions before: ${before.length}`);
  for (const p of before) console.log(`  ${p.symbol}: ${p.qty}`);

  await alpaca.closeAllPositions(); // DELETE /v2/positions?cancel_orders=true
  console.log("Sent close-all + cancel-all. Waiting for fills...");
  await new Promise(r => setTimeout(r, 8000));

  const after = await alpaca.getPositions();
  const acct = await alpaca.getAccount();
  console.log(`\nPositions after: ${after.length}`);
  for (const p of after) console.log(`  ${p.symbol}: ${p.qty}  (STILL OPEN)`);
  console.log(`Equity: $${parseFloat(acct.equity).toFixed(2)} | BP: $${parseFloat(acct.buying_power).toFixed(0)}`);
  console.log(after.length === 0 ? "\nFLAT — clean." : "\nWARNING: still not flat, retry.");
}
main().catch(console.error);
