import { acquireSessionLock } from "../src/engine-stocks/lock";
import fs from "fs";
import path from "path";

const lockPath = path.join(process.cwd(), "data", "stocks-session.lock");
const exists = fs.existsSync(lockPath);
const owner = exists ? JSON.parse(fs.readFileSync(lockPath, "utf8")) : null;
console.log(`Lock file present: ${exists}${owner ? ` (owner pid ${owner.pid}, date ${owner.date})` : ""}`);

const got = acquireSessionLock("2026-06-22");
console.log(`This process (pid ${process.pid}) acquire → ${got ? "ACQUIRED" : "BLOCKED"}`);
console.log(got
  ? (owner ? "WARNING: acquired despite existing lock — check pid liveness logic" : "No live owner, so acquiring is correct.")
  : "BLOCKED correctly — the running engine's session is protected from a concurrent run.");
