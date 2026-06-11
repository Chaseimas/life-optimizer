/** Quick account state check: positions, open orders, today's fills. */
import * as alpaca from "../src/engine-stocks/alpaca";

async function main() {
  const account = await alpaca.getAccount();
  console.log(`Equity: $${parseFloat(account.equity).toFixed(2)} | BP: $${parseFloat(account.buying_power).toFixed(0)}`);

  const positions = await alpaca.getPositions();
  console.log(`\nOPEN POSITIONS: ${positions.length}`);
  for (const p of positions) console.log(`  ${p.symbol}: ${p.qty}`);

  const res = await fetch(`${process.env.ALPACA_TRADING_URL ?? "https://paper-api.alpaca.markets"}/v2/orders?status=open&limit=50`, {
    headers: {
      "APCA-API-KEY-ID": process.env.ALPACA_API_KEY!,
      "APCA-API-SECRET-KEY": process.env.ALPACA_API_SECRET!,
    },
  });
  const openOrders = await res.json();
  console.log(`\nOPEN ORDERS: ${openOrders.length}`);
  for (const o of openOrders) console.log(`  ${o.symbol} ${o.side} ${o.qty} ${o.type} (${o.status}) submitted ${o.submitted_at}`);

  const closed = await alpaca.getClosedOrdersSince(new Date(Date.now() - 18 * 3600000).toISOString());
  console.log(`\nCLOSED ORDERS (last 18h): ${closed.length}`);
  for (const o of closed.slice(0, 30)) {
    console.log(`  ${o.symbol} ${o.side} ${o.qty} ${o.type} → ${o.status}${o.filled_avg_price ? " @ $" + o.filled_avg_price : ""}`);
  }
}
main().catch(console.error);
