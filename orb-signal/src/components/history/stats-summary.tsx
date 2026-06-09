interface Stats {
  total: number;
  wins: number;
  losses: number;
  scratches: number;
  total_r: number;
  avg_r: number | null;
  avg_win_r: number | null;
  avg_loss_r: number | null;
  profit_factor: number;
}

export function StatsSummary({ stats }: { stats: Stats }) {
  const winRate = stats.total > 0 ? (stats.wins / stats.total) * 100 : 0;

  const cards = [
    { label: "Total Trades", value: stats.total.toString() },
    { label: "Win Rate", value: `${winRate.toFixed(0)}%`, color: winRate >= 40 ? "text-green" : "text-red" },
    { label: "Record", value: `${stats.wins}W - ${stats.losses}L - ${stats.scratches}S` },
    { label: "Total R", value: `${stats.total_r >= 0 ? "+" : ""}${stats.total_r.toFixed(2)}R`, color: stats.total_r >= 0 ? "text-green" : "text-red" },
    { label: "Avg R / Trade", value: stats.avg_r?.toFixed(2) ?? "—", color: (stats.avg_r ?? 0) >= 0 ? "text-green" : "text-red" },
    { label: "Profit Factor", value: stats.profit_factor > 0 ? stats.profit_factor.toFixed(2) + "x" : "—", color: stats.profit_factor >= 1.5 ? "text-green" : stats.profit_factor >= 1 ? "text-blue" : "text-red" },
    { label: "Avg Win", value: stats.avg_win_r ? `+${stats.avg_win_r.toFixed(2)}R` : "—", color: "text-green" },
    { label: "Avg Loss", value: stats.avg_loss_r ? `${stats.avg_loss_r.toFixed(2)}R` : "—", color: "text-red" },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      {cards.map(({ label, value, color }) => (
        <div key={label} className="bg-bg-card border border-border rounded-lg p-4">
          <div className="text-xs text-text-muted uppercase">{label}</div>
          <div className={`text-xl font-bold mt-1 ${color ?? ""}`}>{value}</div>
        </div>
      ))}
    </div>
  );
}
