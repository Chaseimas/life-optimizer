export function calcSMA(closes: number[], period: number): number {
  if (closes.length < period) return NaN;
  const slice = closes.slice(-period);
  return slice.reduce((a, b) => a + b, 0) / period;
}

export function calcATR(
  bars: { high: number; low: number; close: number }[],
  period: number
): number {
  if (bars.length < 2) return 0;

  const trueRanges: number[] = [];
  for (let i = 1; i < bars.length; i++) {
    const hl = bars[i].high - bars[i].low;
    const hpc = Math.abs(bars[i].high - bars[i - 1].close);
    const lpc = Math.abs(bars[i].low - bars[i - 1].close);
    trueRanges.push(Math.max(hl, hpc, lpc));
  }

  const slice = trueRanges.slice(-period);
  return slice.reduce((a, b) => a + b, 0) / slice.length;
}

export function calcVWAP(
  bars: { high: number; low: number; close: number; volume: number }[]
): number {
  if (bars.length === 0) return 0;
  let cumVP = 0;
  let cumVol = 0;
  for (const bar of bars) {
    const typical = (bar.high + bar.low + bar.close) / 3;
    cumVP += typical * bar.volume;
    cumVol += bar.volume;
  }
  return cumVol > 0 ? cumVP / cumVol : 0;
}

export function calcEMA(closes: number[], period: number): number {
  if (closes.length < period) return NaN;
  const k = 2 / (period + 1);
  let ema = closes.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < closes.length; i++) {
    ema = closes[i] * k + ema * (1 - k);
  }
  return ema;
}

export function calcSMASlope(smaValues: number[]): number {
  if (smaValues.length < 2) return 0;
  const first = smaValues[0];
  const last = smaValues[smaValues.length - 1];
  return ((last - first) / first) * 100;
}
