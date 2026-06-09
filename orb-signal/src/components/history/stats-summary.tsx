interface Stats {
  total: number;
  wins: number;
  losses: number;
  scratches: number;
  avg_r: number | null;
}

export function StatsSummary({ stats }: { stats: Stats }) {
  const winRate = stats.total > 0 ? (stats.wins / stats.total) * 100 : 0;
  const profitFactor = stats.losses > 0 && stats.avg_r
    ? Math.abs(stats.wins * (stats.avg_r ?? 0)) / Math.abs(stats.losses)
    : 0;

  const cards = [
    { label: "Total Trades", value: stats.total.toString() },
    { label: "Win Rate", value: `${winRate.toFixed(0)}%`, color: winRate >= 50 ? "text-green" : "text-red" },
    { label: "Record", value: `${stats.wins}W - ${stats.losses}L` },
    { label: "Avg R", value: stats.avg_r?.toFixed(2) ?? "—", color: (stats.avg_r ?? 0) >= 0 ? "text-green" : "text-red" },
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
