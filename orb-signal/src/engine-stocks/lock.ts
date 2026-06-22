/**
 * Single-instance daily session lock.
 *
 * 2026-06-22: six engine processes were alive at once and all fired their 9:25
 * session simultaneously — they placed overlapping orders on the same symbols,
 * stacking into oversized NAKED positions and "bracket must be entry" rejects.
 * This lock guarantees only ONE session can run per day. Atomic create (flag wx)
 * makes the acquire race-safe; the freshness guard handles legitimate restarts.
 */
import fs from "fs";
import path from "path";

const LOCK_PATH = path.join(process.cwd(), "data", "stocks-session.lock");

function pidAlive(pid: number): boolean {
  try { process.kill(pid, 0); return true; } catch { return false; }
}

/** Returns true if this process acquired today's session lock; false if another live session owns it. */
export function acquireSessionLock(dateStr: string): boolean {
  // Clear a stale lock (prior day or dead owner) before trying to create.
  try {
    if (fs.existsSync(LOCK_PATH)) {
      const raw = JSON.parse(fs.readFileSync(LOCK_PATH, "utf8"));
      const stale = raw.date !== dateStr || !pidAlive(raw.pid);
      if (!stale && raw.pid !== process.pid) return false; // live owner, today
      if (stale) fs.unlinkSync(LOCK_PATH);
    }
  } catch {
    try { fs.unlinkSync(LOCK_PATH); } catch { /* ignore */ }
  }
  try {
    fs.writeFileSync(
      LOCK_PATH,
      JSON.stringify({ pid: process.pid, date: dateStr, startedAt: new Date().toISOString() }),
      { flag: "wx" } // atomic: fails if another process created it first
    );
    return true;
  } catch {
    return false; // lost the create race to a concurrent process
  }
}

export function releaseSessionLock(): void {
  try {
    if (fs.existsSync(LOCK_PATH)) {
      const raw = JSON.parse(fs.readFileSync(LOCK_PATH, "utf8"));
      if (raw.pid === process.pid) fs.unlinkSync(LOCK_PATH);
    }
  } catch { /* ignore */ }
}
