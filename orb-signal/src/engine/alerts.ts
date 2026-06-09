import { sendDiscordMessage } from "@/lib/discord";
import type { DailyContext, OpeningRange, Signal, ActiveSignal, Outcome } from "@/lib/types";

export async function alertSessionStart(contexts: DailyContext[]): Promise<void> {
  const lines = ["**ORB Session Starting**"];
  lines.push(`Watching: ${contexts.map(c => c.ticker).join(", ")}`);
  lines.push("Timeframes: 5 / 10 min (auto-pick best)");

  for (const ctx of contexts) {
    const trend = ctx.premarketPrice > ctx.sma20 ? "above" : "below";
    const gapStr = `gap ${ctx.gapPct >= 0 ? "+" : ""}${ctx.gapPct.toFixed(1)}% ${ctx.gapDirection}`;
    const slopeStr = `slope: ${ctx.smaSlope >= 0 ? "+" : ""}${ctx.smaSlope.toFixed(1)}%`;
    const stagnant = Math.abs(ctx.smaSlope) < 0.5 ? " (stagnant)" : " (trending)";
    lines.push(`${ctx.ticker}: ${trend} 20-SMA | ${gapStr} | ${slopeStr}${stagnant}`);
  }

  await sendDiscordMessage(lines.join("\n"));
}

export async function alertRangeSet(range: OpeningRange, context: DailyContext): Promise<void> {
  const pct = range.rangeAtrPct.toFixed(0);
  const volRatio = range.volume > 0 ? "OK" : "low";
  const msg = [
    `**${range.ticker} ${range.timeframe}-min Range Set  [${range.grade}]**`,
    `High: $${range.rangeHigh.toLocaleString()} | Low: $${range.rangeLow.toLocaleString()} | Width: $${range.rangeWidth.toLocaleString()}`,
    `VWAP: $${range.vwapAtClose.toLocaleString()} | ATR: $${context.atr14.toLocaleString()} (range = ${pct}%)`,
    range.grade === "SKIP" ? `Skipped: ${range.skipReason}` : "Watching for breakout...",
  ].join("\n");

  await sendDiscordMessage(msg);
}

export async function alertSignal(signal: Signal, rank: number, totalSelected: number): Promise<void> {
  const dir = signal.direction === "LONG" ? "LONG" : "SHORT";
  const gapStr = signal.gapAligned ? "(with gap)" : "(counter-gap)";
  const msg = [
    `**ORB ${dir} — ${signal.ticker} ${signal.timeframe}-min  [${signal.grade}]  #${rank} SETUP**`,
    `Entry:   $${signal.entryPrice.toLocaleString()}`,
    `Stop:    $${signal.stopPrice.toLocaleString()} (range ${signal.direction === "LONG" ? "low" : "high"})`,
    `Target:  $${signal.targetPrice.toLocaleString()} (measured move, 1R)`,
    `Risk:    $${signal.risk.toLocaleString()}`,
    `---`,
    `${signal.direction === "LONG" ? "Above" : "Below"} VWAP ($${signal.vwapAtEntry.toLocaleString()})`,
    `Trend: ${signal.trendAligned ? "with" : "against"} 20-SMA, slope ${signal.smaSlope >= 0 ? "+" : ""}${signal.smaSlope.toFixed(1)}%`,
    `Gap: ${signal.gapPct >= 0 ? "+" : ""}${signal.gapPct.toFixed(1)}% ${gapStr}`,
    `Breakout vol: ${(signal.breakoutVolumeRatio * 100).toFixed(0)}% of avg`,
    `Score: ${signal.rankingScore.toFixed(1)} / 12`,
    `---`,
    `Trade ${rank} of ${totalSelected} today.`,
  ].join("\n");

  await sendDiscordMessage(msg);
}

export async function alertBreakevenHit(signal: ActiveSignal): Promise<void> {
  const dir = signal.direction === "LONG" ? "LONG" : "SHORT";
  const bestR = signal.direction === "LONG"
    ? (signal.maxFavorable - signal.entryPrice) / signal.risk
    : (signal.entryPrice - signal.maxFavorable) / signal.risk;
  const msg = [
    `**${signal.ticker} ${dir} — Stop → breakeven ($${signal.entryPrice.toLocaleString()})**`,
    `Reached +${bestR.toFixed(2)}R, protecting at 0R. Target still $${signal.targetPrice.toLocaleString()}.`,
  ].join("\n");

  await sendDiscordMessage(msg);
}

export async function alertTargetHit(signal: ActiveSignal): Promise<void> {
  const dir = signal.direction === "LONG" ? "LONG" : "SHORT";
  const pnl = signal.direction === "LONG"
    ? signal.targetPrice - signal.entryPrice
    : signal.entryPrice - signal.targetPrice;
  const msg = [
    `**${signal.ticker} ${dir} — Target hit at $${signal.targetPrice.toLocaleString()} (+$${pnl.toLocaleString()}, 1R)**`,
    `Stop moved to breakeven ($${signal.entryPrice.toLocaleString()}).`,
    `Trail ${signal.direction === "LONG" ? "below" : "above"} 9-EMA for the runner.`,
  ].join("\n");

  await sendDiscordMessage(msg);
}

export async function alertTradeClose(signal: ActiveSignal): Promise<void> {
  const dir = signal.direction === "LONG" ? "LONG" : "SHORT";
  const pnl = signal.direction === "LONG"
    ? (signal.exitPrice ?? signal.entryPrice) - signal.entryPrice
    : signal.entryPrice - (signal.exitPrice ?? signal.entryPrice);
  const outcome = signal.outcome ?? "SCRATCH";
  const emoji = outcome === "WIN" ? "WIN" : outcome === "LOSS" ? "LOSS" : "SCRATCH";
  const msg = [
    `**${signal.ticker} ${dir} — Done.**`,
    `Exit: $${signal.exitPrice?.toLocaleString()} (${signal.exitType})`,
    `Result: ${pnl >= 0 ? "+" : ""}$${pnl.toLocaleString()} (${signal.rMultiple?.toFixed(1)}R) ${emoji}`,
  ].join("\n");

  await sendDiscordMessage(msg);
}

export async function alertNoTrade(reasons: { ticker: string; reason: string }[]): Promise<void> {
  const lines = ["**No trade today.**"];
  for (const r of reasons) lines.push(`${r.ticker}: ${r.reason}`);
  lines.push("No setup worth the risk. Sitting out.");
  await sendDiscordMessage(lines.join("\n"));
}

export async function alertDailySummary(
  signals: ActiveSignal[],
  skipped: { ticker: string; reason: string }[],
  stats: { winRate: number; wins: number; losses: number; totalR: number }
): Promise<void> {
  const date = new Date().toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const lines = [`**ORB Daily Summary — ${date}**`];

  if (signals.length === 0) {
    lines.push("No trades taken today.");
  } else {
    let dayR = 0;
    for (let i = 0; i < signals.length; i++) {
      const s = signals[i];
      const pnl = s.direction === "LONG"
        ? (s.exitPrice ?? s.entryPrice) - s.entryPrice
        : s.entryPrice - (s.exitPrice ?? s.entryPrice);
      const r = s.rMultiple ?? 0;
      dayR += r;
      lines.push(`Trade ${i + 1}: ${s.ticker} ${s.direction} ${s.timeframe}-min [${s.grade}] → ${s.outcome} ${pnl >= 0 ? "+" : ""}$${pnl.toFixed(0)} (${r >= 0 ? "+" : ""}${r.toFixed(2)}R)`);
    }
    lines.push(`**Day total: ${dayR >= 0 ? "+" : ""}${dayR.toFixed(2)}R**`);
  }

  lines.push("---");
  for (const s of skipped) lines.push(`Skipped: ${s.ticker} (${s.reason})`);
  lines.push("---");
  lines.push(`Running: ${stats.winRate.toFixed(0)}% win rate (${stats.wins}W-${stats.losses}L) | Cumulative: ${stats.totalR >= 0 ? "+" : ""}${stats.totalR.toFixed(2)}R`);

  await sendDiscordMessage(lines.join("\n"));
}
