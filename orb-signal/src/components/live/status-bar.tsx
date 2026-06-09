export function StatusBar({ status, tradesActive }: { status: string; tradesActive: number }) {
  const color = status === "MONITORING" ? "text-green" :
    status === "TRACKING" ? "text-blue" :
    status === "CLOSED" ? "text-text-muted" : "text-text-secondary";

  return (
    <div className="flex items-center justify-between bg-bg-card border border-border rounded-lg p-4 mb-6">
      <div className="flex items-center gap-3">
        <div className={`w-2 h-2 rounded-full ${status === "MONITORING" || status === "TRACKING" ? "bg-green animate-pulse" : "bg-text-muted"}`} />
        <span className={`font-medium ${color}`}>{status}</span>
      </div>
      <div className="text-sm text-text-secondary">
        {tradesActive > 0 ? `${tradesActive} active trade(s)` : "Waiting for setup"}
      </div>
    </div>
  );
}
