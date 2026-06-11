/** Fetch the orphan TSLA/AMD orders with nested legs to recover exact exit fills. */
import * as alpaca from "../src/engine-stocks/alpaca";

async function main() {
  const closed = await alpaca.getClosedOrdersSince(new Date(Date.now() - 18 * 3600000).toISOString());
  for (const o of closed) {
    if (o.symbol !== "TSLA" && o.symbol !== "AMD") continue;
    console.log(`\n${o.symbol} ${o.side} ${o.qty} entry: ${o.status} @ ${o.filled_avg_price} (filled_at ${o.filled_at})`);
    for (const leg of o.legs ?? []) {
      console.log(`  leg ${leg.type}: ${leg.status}${leg.filled_avg_price ? " @ " + leg.filled_avg_price : ""}${leg.filled_at ? " at " + leg.filled_at : ""}`);
    }
  }
}
main().catch(console.error);
