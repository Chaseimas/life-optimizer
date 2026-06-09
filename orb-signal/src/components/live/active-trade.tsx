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
  target_hit: number | null;
}

export function ActiveTrade({ signal }: { signal: SignalRow }) {
  const pnl = signal.exit_price
    ? (signal.direction === "LONG" ? signal.exit_price - signal.entry_price : signal.entry_price - signal.exit_price)
    : 0;
  const color = signal.outcome === "WIN" ? "text-green" :
    signal.outcome === "LOSS" ? "text-red" : "text-blue";
  const isBreakeven = Math.abs(signal.stop_price - signal.entry_price) < 0.01;
  const isTrailing = signal.target_hit === 1;

  // Status badge
  let statusText = "Active";
  let statusColor = "bg-blue/20 text-blue";
  if (signal.outcome) {
    statusText = signal.outcome;
    statusColor = signal.outcome === "WIN" ? "bg-green/20 text-green" :
      signal.outcome === "LOSS" ? "bg-red/20 text-red" : "bg-gray-500/20 text-text-muted";
  } else if (isTrailing) {
    statusText = "Trailing (1R hit)";
    statusColor = "bg-green/20 text-green";
  } else if (isBreakeven) {
    statusText = "Stop → Breakeven";
    statusColor = "bg-blue/20 text-blue";
  }

  return (
    <div className="bg-bg-card border border-border rounded-lg p-4 mt-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold">
          {signal.direction} — {signal.ticker} {signal.timeframe}m [{signal.grade}]
        </h3>
        <span className={`text-xs font-bold px-2 py-1 rounded ${statusColor}`}>{statusText}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
        <div>
          <div className="text-text-muted">Entry</div>
          <div>${signal.entry_price.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-text-muted">Stop{isBreakeven ? " (BE)" : ""}</div>
          <div className={isBreakeven ? "text-blue" : "text-red"}>${signal.stop_price.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-text-muted">Target</div>
          <div className={isTrailing ? "text-green line-through" : "text-green"}>${signal.target_price.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-text-muted">Risk</div>
          <div>${signal.risk.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-text-muted">Score</div>
          <div>{signal.ranking_score.toFixed(1)} / 12</div>
        </div>
      </div>
      {signal.outcome && (
        <div className={`mt-3 text-sm font-medium ${color}`}>
          Result: {pnl >= 0 ? "+" : ""}${pnl.toFixed(2)} ({signal.r_multiple != null ? `${signal.r_multiple >= 0 ? "+" : ""}${signal.r_multiple.toFixed(2)}R` : "—"})
        </div>
      )}
    </div>
  );
}
