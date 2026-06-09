interface DailyReturn {
  date: string;
  trades: number;
  wins: number;
  losses: number;
  day_r: number;
}

export function EquityCurve({ dailyReturns }: { dailyReturns: DailyReturn[] }) {
  if (dailyReturns.length === 0) return null;

  // Build cumulative R series
  const points: { date: string; cumR: number; dayR: number; trades: number }[] = [];
  let cumR = 0;
  for (const d of dailyReturns) {
    cumR += d.day_r;
    points.push({ date: d.date, cumR, dayR: d.day_r, trades: d.trades });
  }

  // SVG dimensions
  const width = 800;
  const height = 200;
  const padding = { top: 20, right: 20, bottom: 30, left: 50 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  // Scale
  const minR = Math.min(0, ...points.map(p => p.cumR));
  const maxR = Math.max(0, ...points.map(p => p.cumR));
  const range = maxR - minR || 1;

  const xScale = (i: number) => padding.left + (i / Math.max(1, points.length - 1)) * chartW;
  const yScale = (r: number) => padding.top + chartH - ((r - minR) / range) * chartH;

  // Build SVG path
  const pathD = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${xScale(i).toFixed(1)} ${yScale(p.cumR).toFixed(1)}`)
    .join(" ");

  // Fill area under curve
  const areaD = pathD +
    ` L ${xScale(points.length - 1).toFixed(1)} ${yScale(0).toFixed(1)}` +
    ` L ${xScale(0).toFixed(1)} ${yScale(0).toFixed(1)} Z`;

  // Zero line
  const zeroY = yScale(0);

  // Y-axis labels
  const yTicks = [minR, minR + range / 2, maxR].map(v => ({
    value: v,
    y: yScale(v),
    label: `${v >= 0 ? "+" : ""}${v.toFixed(1)}R`,
  }));

  // X-axis: show first, last, and a few middle dates
  const xLabels: { x: number; label: string }[] = [];
  const step = Math.max(1, Math.floor(points.length / 5));
  for (let i = 0; i < points.length; i += step) {
    xLabels.push({ x: xScale(i), label: points[i].date.slice(5) }); // MM-DD
  }
  if (points.length > 1) {
    const last = points.length - 1;
    if (last % step !== 0) {
      xLabels.push({ x: xScale(last), label: points[last].date.slice(5) });
    }
  }

  const finalR = points[points.length - 1].cumR;
  const lineColor = finalR >= 0 ? "#00c853" : "#ff3d00";
  const fillColor = finalR >= 0 ? "rgba(0,200,83,0.1)" : "rgba(255,61,0,0.1)";

  return (
    <div className="bg-bg-card border border-border rounded-lg p-4 mb-6">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium text-text-muted uppercase">Equity Curve</h3>
        <span className={`text-sm font-bold ${finalR >= 0 ? "text-green" : "text-red"}`}>
          {finalR >= 0 ? "+" : ""}{finalR.toFixed(2)}R over {points.length} days
        </span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ maxHeight: 220 }}>
        {/* Zero line */}
        <line
          x1={padding.left} y1={zeroY}
          x2={width - padding.right} y2={zeroY}
          stroke="#2d3748" strokeWidth="1" strokeDasharray="4,4"
        />
        {/* Y-axis labels */}
        {yTicks.map((t, i) => (
          <text key={i} x={padding.left - 8} y={t.y + 4}
            fill="#8b9ab5" fontSize="10" textAnchor="end">
            {t.label}
          </text>
        ))}
        {/* X-axis labels */}
        {xLabels.map((t, i) => (
          <text key={i} x={t.x} y={height - 5}
            fill="#8b9ab5" fontSize="10" textAnchor="middle">
            {t.label}
          </text>
        ))}
        {/* Area fill */}
        <path d={areaD} fill={fillColor} />
        {/* Line */}
        <path d={pathD} fill="none" stroke={lineColor} strokeWidth="2" />
        {/* Data points */}
        {points.map((p, i) => (
          <circle key={i} cx={xScale(i)} cy={yScale(p.cumR)} r="3"
            fill={p.dayR >= 0 ? "#00c853" : "#ff3d00"} stroke="#131722" strokeWidth="1" />
        ))}
      </svg>
    </div>
  );
}
