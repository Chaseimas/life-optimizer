import cron from "node-cron";
import { runStockSession } from "./session";
import { STOCKS_CONFIG } from "./config";
import * as alpaca from "./alpaca";
import { getDb } from "@/lib/db/index";

console.log("[stocks-engine] ORB Stock Paper-Trading Engine starting...");
getDb();
console.log("[stocks-engine] Database initialized");

// 9:25 AM ET weekdays — session handles holiday detection itself
cron.schedule("25 9 * * 1-5", async () => {
  console.log("[stocks-engine] 9:25 AM ET — starting stock session");
  try {
    await runStockSession();
  } catch (err) {
    console.error("[stocks-engine] Session error:", err);
  }
}, { timezone: "America/New_York" });

console.log(`[stocks-engine] Scheduled: 9:25 AM ET Mon-Fri | Universe: ${STOCKS_CONFIG.TICKERS.join(", ")}`);

if (process.argv.includes("--dry")) {
  (async () => {
    console.log("[stocks-engine] DRY RUN — checking connectivity");
    const account = await alpaca.getAccount();
    console.log(`  Paper account: ${account.status} | equity $${parseFloat(account.equity).toFixed(0)} | buying power $${parseFloat(account.buying_power).toFixed(0)}`);
    const clock = await alpaca.getClock();
    console.log(`  Market open now: ${clock.is_open} | next open: ${clock.next_open} | next close: ${clock.next_close}`);
    const bars = await alpaca.getTodayBars([...STOCKS_CONFIG.TICKERS], new Date(Date.now() - 24 * 3600000).toISOString());
    for (const [sym, b] of bars) console.log(`  ${sym}: ${b.length} bars in last 24h`);
    console.log("[stocks-engine] Dry run OK.");
    process.exit(0);
  })().catch(err => { console.error("[stocks-engine] Dry run failed:", err); process.exit(1); });
}

if (process.argv.includes("--now")) {
  console.log("[stocks-engine] --now flag — running session immediately");
  runStockSession().then(() => console.log("[stocks-engine] Immediate session complete"));
} else if (!process.argv.includes("--dry")) {
  // Catch-up: if the process starts (or the PC wakes) mid-session, don't wait
  // for tomorrow's cron — run now. The session's freshness guard prevents
  // stale entries; worst case it posts ranges + "no trades" and flattens nothing.
  const d = new Date();
  const m = d.getUTCMonth(), day = d.getUTCDate();
  let off = 5;
  if (m > 2 && m < 10) off = 4;
  else if (m === 2) off = day >= 9 ? 4 : 5;
  else if (m === 10) off = day < 2 ? 4 : 5;
  const etMin = (d.getUTCHours() - off) * 60 + d.getUTCMinutes();
  const dow = new Date(d.getTime() - off * 3600000).getUTCDay();
  if (dow >= 1 && dow <= 5 && etMin >= 9 * 60 + 25 && etMin < 15 * 60 + 55) {
    console.log("[stocks-engine] Started mid-session — running catch-up session now");
    runStockSession().then(() => console.log("[stocks-engine] Catch-up session complete"));
  }
}
