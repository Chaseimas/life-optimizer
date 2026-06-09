interface RangeCardProps {
  ticker: string;
  timeframe: number;
  rangeHigh: number | null;
  rangeLow: number | null;
  grade: string | null;
  status: string;
  isSelected: boolean;
}

export function RangeCard({ ticker, timeframe, rangeHigh, rangeLow, grade, status, isSelected }: RangeCardProps) {
  const borderColor = isSelected ? "border-green" :
    grade === "SKIP" ? "border-red/30" :
    status === "Building..." ? "border-blue/30" : "border-border";

  return (
    <div className={`bg-bg-card border ${borderColor} rounded-lg p-3`}>
      <div className="flex items-center justify-between mb-2">
        <span className="font-medium text-sm">{ticker} {timeframe}m</span>
        {grade && (
          <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
            grade === "A" ? "bg-green/20 text-green" :
            grade === "B" ? "bg-blue/20 text-blue" :
            grade === "C" ? "bg-text-muted/20 text-text-secondary" :
            "bg-red/20 text-red"
          }`}>
            {grade}
          </span>
        )}
      </div>
      {rangeHigh !== null && rangeLow !== null ? (
        <div className="text-xs text-text-secondary">
          <div>H: ${rangeHigh.toLocaleString()}</div>
          <div>L: ${rangeLow.toLocaleString()}</div>
          <div className="mt-1 text-text-muted">{status}</div>
        </div>
      ) : (
        <div className="text-xs text-text-muted">{status}</div>
      )}
    </div>
  );
}
