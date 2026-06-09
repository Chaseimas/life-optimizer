import { StatsSummary } from "@/components/history/stats-summary";
import { SignalTable } from "@/components/history/signal-table";
import { getSignalHistory, getPerformanceStats } from "@/lib/db/queries/signals";

export const dynamic = "force-dynamic";

export default function HistoryPage() {
  const signals = getSignalHistory(100, 0) as any[];
  const stats = (getPerformanceStats() ?? { total: 0, wins: 0, losses: 0, scratches: 0, avg_r: null }) as any;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">History</h1>
      <StatsSummary stats={stats} />
      <SignalTable signals={signals} />
    </div>
  );
}
