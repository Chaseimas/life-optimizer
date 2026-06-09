interface SignalRow {
  id: number;
  date: string;
  ticker: string;
  timeframe: number;
  direction: string;
  grade: string;
  entry_price: number;
  exit_price: number | null;
  outcome: string | null;
  r_multiple: number | null;
  exit_type: string | null;
  ranking_score: number;
}

export function SignalTable({ signals }: { signals: SignalRow[] }) {
  return (
    <div className="bg-bg-card border border-border rounded-lg overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-text-muted text-left">
            <th className="p-3">Date</th>
            <th className="p-3">Ticker</th>
            <th className="p-3">TF</th>
            <th className="p-3">Dir</th>
            <th className="p-3">Grade</th>
            <th className="p-3">Entry</th>
            <th className="p-3">Exit</th>
            <th className="p-3">Result</th>
            <th className="p-3">R</th>
            <th className="p-3">Exit Type</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s) => (
            <tr key={s.id} className="border-b border-border/50 hover:bg-bg-secondary/50">
              <td className="p-3 text-text-secondary">{s.date}</td>
              <td className="p-3 font-medium">{s.ticker}</td>
              <td className="p-3">{s.timeframe}m</td>
              <td className={`p-3 ${s.direction === "LONG" ? "text-green" : "text-red"}`}>{s.direction}</td>
              <td className="p-3">{s.grade}</td>
              <td className="p-3">${s.entry_price.toLocaleString()}</td>
              <td className="p-3">{s.exit_price ? `$${s.exit_price.toLocaleString()}` : "—"}</td>
              <td className={`p-3 font-medium ${
                s.outcome === "WIN" ? "text-green" : s.outcome === "LOSS" ? "text-red" : "text-text-muted"
              }`}>
                {s.outcome ?? "—"}
              </td>
              <td className="p-3">{s.r_multiple?.toFixed(1) ?? "—"}</td>
              <td className="p-3 text-text-secondary">{s.exit_type ?? "—"}</td>
            </tr>
          ))}
          {signals.length === 0 && (
            <tr>
              <td colSpan={10} className="p-8 text-center text-text-muted">No signal history yet.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
