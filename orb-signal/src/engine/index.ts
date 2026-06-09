import cron from "node-cron";
import { SessionManager } from "./session";
import { getDb } from "@/lib/db/index";

console.log("[engine] ORB Signal Engine starting...");

getDb();
console.log("[engine] Database initialized");

cron.schedule("0 13 * * 1-5", async () => {
  console.log("[engine] 9:00 AM ET — Starting daily session");
  const session = new SessionManager();
  await session.runSession();
  console.log("[engine] Session complete");
}, {
  timezone: "America/New_York",
});

console.log("[engine] Scheduled: daily session at 9:00 AM ET (Mon-Fri)");
console.log("[engine] Waiting for next session...");

if (process.argv.includes("--now")) {
  console.log("[engine] --now flag detected, running session immediately");
  const session = new SessionManager();
  session.runSession().then(() => {
    console.log("[engine] Immediate session complete");
  });
}
