import { StatsSummary } from "@/components/history/stats-summary";
import { EquityCurve } from "@/components/history/equity-curve";
import { SignalTable } from "@/components/history/signal-table";
import { getSignalHistory, getPerformanceStats, getDailyReturns } from "@/lib/db/queries/signals";

export const dynamic = "force-dynamic";

export default function HistoryPage() {
  const signals = getSignalHistory(100, 0) as any[];
  const stats = (getPerformanceStats() ?? {
    total: 0, wins: 0, losses: 0, scratches: 0,
    total_r: 0, avg_r: null, avg_win_r: null, avg_loss_r: null, profit_factor: 0,
  }) as any;
  const dailyReturns = getDailyReturns();

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">History</h1>
      <StatsSummary stats={stats} />
      <EquityCurve dailyReturns={dailyReturns} />
      <SignalTable signals={signals} />
    </div>
  );
}
