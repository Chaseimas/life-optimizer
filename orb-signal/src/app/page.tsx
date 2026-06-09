import { StatusBar } from "@/components/live/status-bar";
import { RangeGrid } from "@/components/live/range-grid";
import { ActiveTrade } from "@/components/live/active-trade";
import { getRangesByDate } from "@/lib/db/queries/ranges";
import { getSignalsByDate } from "@/lib/db/queries/signals";

export const dynamic = "force-dynamic";

export default function LiveView() {
  const today = new Date().toISOString().split("T")[0];
  const ranges = getRangesByDate(today) as any[];
  const signals = getSignalsByDate(today) as any[];
  const activeSignals = signals.filter((s: any) => s.was_selected === 1);

  const hasRanges = ranges.length > 0;
  const hasActive = activeSignals.some((s: any) => !s.outcome);
  const allDone = activeSignals.length > 0 && activeSignals.every((s: any) => s.outcome);
  const status = allDone ? "CLOSED" : hasActive ? "TRACKING" : hasRanges ? "MONITORING" : "IDLE";

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Live View</h1>
      <StatusBar status={status} tradesActive={activeSignals.filter((s: any) => !s.outcome).length} />
      <RangeGrid ranges={ranges} />
      {activeSignals.map((signal: any) => (
        <ActiveTrade key={signal.id} signal={signal} />
      ))}
      {!hasRanges && (
        <div className="text-center text-text-muted mt-12">
          <p>No session data for today yet.</p>
          <p className="text-sm mt-1">The engine starts at 9:00 AM ET on trading days.</p>
        </div>
      )}
    </div>
  );
}
