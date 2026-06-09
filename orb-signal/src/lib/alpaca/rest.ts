import { ALPACA_REST_URL } from "../constants";
import type { AlpacaBar } from "../types";

function headers(): Record<string, string> {
  return {
    "APCA-API-KEY-ID": process.env.ALPACA_API_KEY!,
    "APCA-API-SECRET-KEY": process.env.ALPACA_API_SECRET!,
  };
}

export async function getCryptoBars(
  symbol: string,
  timeframe: string,
  start: string,
  end?: string,
  limit = 1000
): Promise<AlpacaBar[]> {
  const params = new URLSearchParams({
    symbols: symbol,
    timeframe: timeframe,
    start: start,
    limit: String(limit),
    sort: "asc",
  });
  if (end) params.set("end", end);

  const url = `${ALPACA_REST_URL}/v1beta3/crypto/us/bars?${params}`;
  const res = await fetch(url, { headers: headers() });

  if (!res.ok) {
    throw new Error(`Alpaca REST error ${res.status}: ${await res.text()}`);
  }

  const data = await res.json();
  return data.bars?.[symbol] ?? [];
}

export async function getLatestCryptoTrade(symbol: string): Promise<{ price: number; timestamp: string } | null> {
  const url = `${ALPACA_REST_URL}/v1beta3/crypto/us/latest/trades?symbols=${symbol}`;
  const res = await fetch(url, { headers: headers() });
  if (!res.ok) return null;
  const data = await res.json();
  const trade = data.trades?.[symbol];
  return trade ? { price: trade.p, timestamp: trade.t } : null;
}
