/**
 * Discord alerts for the stock paper-trading engine.
 * Uses the same DISCORD_WEBHOOK_URL as the crypto engine.
 */

const GREEN = 0x00c853;
const RED = 0xff3d00;
const BLUE = 0x4f8fea;
const GRAY = 0x9e9e9e;

async function send(embed: { title: string; description: string; color: number }): Promise<void> {
  const url = process.env.DISCORD_WEBHOOK_URL;
  if (!url) return;
  try {
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ embeds: [{ ...embed, timestamp: new Date().toISOString() }] }),
    });
  } catch (err) {
    console.error("[stocks-alerts] Discord error:", err);
  }
}

export async function alertSessionStart(equity: number, ranges: {
  ticker: string; high: number; low: number; dir: string | null; skipped: string | null;
}[]): Promise<void> {
  const lines = ranges.map(r =>
    r.skipped
      ? `~~${r.ticker}~~ — skipped (${r.skipped})`
      : `**${r.ticker}** ${r.dir} watch | range $${r.low.toFixed(2)} – $${r.high.toFixed(2)}`
  );
  await send({
    title: "📈 Stock ORB session — ranges set (5-min)",
    description: `Paper equity: $${equity.toLocaleString("en-US", { maximumFractionDigits: 0 })}\n\n${lines.join("\n")}\n\nEntries until 10:30 ET · 3R target · EOD flatten 3:55 PM`,
    color: BLUE,
  });
}

export async function alertEntry(t: {
  ticker: string; direction: string; qty: number;
  fillPrice: number; stopPrice: number; targetPrice: number; riskDollars: number;
}): Promise<void> {
  await send({
    title: `🎯 ENTRY — ${t.ticker} ${t.direction}`,
    description:
      `Filled: **$${t.fillPrice.toFixed(2)}** × ${t.qty} shares\n` +
      `Stop: $${t.stopPrice.toFixed(2)} | Target (3R): $${t.targetPrice.toFixed(2)}\n` +
      `Risk: ~$${t.riskDollars.toFixed(0)}`,
    color: t.direction === "LONG" ? GREEN : RED,
  });
}

export async function alertExit(t: {
  ticker: string; direction: string; exitType: string;
  fillPrice: number; exitPrice: number; rMultiple: number; pnlDollars: number;
}): Promise<void> {
  const sign = t.rMultiple >= 0 ? "+" : "";
  await send({
    title: `${t.rMultiple >= 0.2 ? "✅" : t.rMultiple <= -0.2 ? "❌" : "➖"} EXIT — ${t.ticker} ${t.direction} (${t.exitType})`,
    description:
      `$${t.fillPrice.toFixed(2)} → $${t.exitPrice.toFixed(2)}\n` +
      `**${sign}${t.rMultiple.toFixed(2)}R** (${sign}$${Math.abs(t.pnlDollars) < 0.005 ? "0" : t.pnlDollars.toFixed(0)})`,
    color: t.rMultiple >= 0.2 ? GREEN : t.rMultiple <= -0.2 ? RED : GRAY,
  });
}

export async function alertSummary(s: {
  trades: { ticker: string; direction: string; rMultiple: number; exitType: string }[];
  dayR: number; dayPnl: number; equity: number;
}): Promise<void> {
  const lines = s.trades.length === 0
    ? ["No trades today."]
    : s.trades.map(t => `${t.rMultiple >= 0.2 ? "✅" : t.rMultiple <= -0.2 ? "❌" : "➖"} ${t.ticker} ${t.direction}: ${t.rMultiple >= 0 ? "+" : ""}${t.rMultiple.toFixed(2)}R (${t.exitType})`);
  await send({
    title: "🌙 Stock session complete",
    description:
      `${lines.join("\n")}\n\n` +
      `**Day: ${s.dayR >= 0 ? "+" : ""}${s.dayR.toFixed(2)}R (${s.dayPnl >= 0 ? "+" : ""}$${s.dayPnl.toFixed(0)})**\n` +
      `Paper equity: $${s.equity.toLocaleString("en-US", { maximumFractionDigits: 0 })}`,
    color: s.dayR >= 0 ? GREEN : RED,
  });
}

export async function alertError(msg: string): Promise<void> {
  await send({ title: "⚠️ Stock engine error", description: msg.slice(0, 1000), color: RED });
}
