import { RangeCard } from "./range-card";

interface Range {
  ticker: string;
  timeframe: number;
  range_high: number;
  range_low: number;
  quality_grade: string;
}

export function RangeGrid({ ranges }: { ranges: Range[] }) {
  const tickers = ["BTC", "ETH", "SOL"];
  const timeframes = [5, 10, 15];

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">Opening Ranges</h2>
      <div className="grid grid-cols-3 gap-3">
        {tickers.map(ticker =>
          timeframes.map(tf => {
            const range = ranges.find(r => r.ticker === ticker && r.timeframe === tf);
            return (
              <RangeCard
                key={`${ticker}-${tf}`}
                ticker={ticker}
                timeframe={tf}
                rangeHigh={range?.range_high ?? null}
                rangeLow={range?.range_low ?? null}
                grade={range?.quality_grade ?? null}
                status={range ? (range.quality_grade === "SKIP" ? "Skipped" : "Watching") : "Waiting..."}
                isSelected={false}
              />
            );
          })
        )}
      </div>
    </div>
  );
}
