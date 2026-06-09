interface SignalRow {
  ticker: string;
  timeframe: number;
  direction: string;
  grade: string;
  entry_price: number;
  stop_price: number;
  target_price: number;
  risk: number;
  outcome: string | null;
  exit_price: number | null;
  r_multiple: number | null;
  ranking_score: number;
}

export function ActiveTrade({ signal }: { signal: SignalRow }) {
  const pnl = signal.exit_price
    ? (signal.direction === "LONG" ? signal.exit_price - signal.entry_price : signal.entry_price - signal.exit_price)
    : 0;
  const color = signal.outcome === "WIN" ? "text-green" :
    signal.outcome === "LOSS" ? "text-red" : "text-blue";

  return (
    <div className="bg-bg-card border border-border rounded-lg p-4 mt-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold">
          {signal.direction} — {signal.ticker} {signal.timeframe}m [{signal.grade}]
        </h3>
        {signal.outcome && (
          <span className={`font-bold ${color}`}>{signal.outcome}</span>
        )}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <div>
          <div className="text-text-muted">Entry</div>
          <div>${signal.entry_price.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-text-muted">Stop</div>
          <div className="text-red">${signal.stop_price.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-text-muted">Target</div>
          <div className="text-green">${signal.target_price.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-text-muted">Score</div>
          <div>{signal.ranking_score.toFixed(1)} / 12</div>
        </div>
      </div>
      {signal.outcome && (
        <div className={`mt-3 text-sm font-medium ${color}`}>
          Result: {pnl >= 0 ? "+" : ""}${pnl.toFixed(2)} ({signal.r_multiple?.toFixed(1)}R)
        </div>
      )}
    </div>
  );
}
