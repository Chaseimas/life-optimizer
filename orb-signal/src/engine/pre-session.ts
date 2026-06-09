import { getCryptoBars, getLatestCryptoTrade } from "@/lib/alpaca/rest";
import { calcSMA, calcATR, calcSMASlope } from "@/lib/indicators";
import { TICKERS, TICKER_SHORT } from "@/lib/constants";
import type { DailyContext, Ticker, GapDirection } from "@/lib/types";

export async function gatherPreSessionContext(): Promise<DailyContext[]> {
  const contexts: DailyContext[] = [];

  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 40);

  for (const ticker of TICKERS) {
    const short = TICKER_SHORT[ticker];

    const bars = await getCryptoBars(
      ticker,
      "1Day",
      start.toISOString(),
      end.toISOString()
    );

    if (bars.length < 21) {
      console.warn(`[pre-session] ${short}: only ${bars.length} daily bars, need 21+`);
      continue;
    }

    const closes = bars.map(b => b.c);
    const hlcBars = bars.map(b => ({ high: b.h, low: b.l, close: b.c }));

    const sma20 = calcSMA(closes, 20);
    const atr14 = calcATR(hlcBars, 14);

    const smaValues: number[] = [];
    for (let i = Math.max(0, bars.length - 6); i < bars.length; i++) {
      const slice = bars.slice(0, i + 1).map(b => b.c);
      if (slice.length >= 20) {
        smaValues.push(calcSMA(slice, 20));
      }
    }
    const smaSlope = calcSMASlope(smaValues);

    const priorDay = bars[bars.length - 2];
    const latestTrade = await getLatestCryptoTrade(ticker);
    const premarketPrice = latestTrade?.price ?? bars[bars.length - 1].c;

    const gapPct = ((premarketPrice - priorDay.c) / priorDay.c) * 100;
    const gapDirection: GapDirection =
      gapPct > 0.1 ? "UP" : gapPct < -0.1 ? "DOWN" : "FLAT";

    contexts.push({
      ticker: short,
      priorDayHigh: priorDay.h,
      priorDayLow: priorDay.l,
      priorDayClose: priorDay.c,
      premarketPrice,
      sma20,
      smaSlope,
      atr14,
      gapPct,
      gapDirection,
    });
  }

  return contexts;
}
