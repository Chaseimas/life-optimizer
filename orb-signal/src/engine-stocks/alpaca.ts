/**
 * Alpaca paper-trading client (REST) + IEX stock bars.
 * Trading goes to paper-api.alpaca.markets; market data to data.alpaca.markets.
 */

import { ALPACA_REST_URL } from "@/lib/constants";
import { TRADING_URL } from "./config";
import type { AlpacaBar } from "@/lib/types";

function headers() {
  return {
    "APCA-API-KEY-ID": process.env.ALPACA_API_KEY!,
    "APCA-API-SECRET-KEY": process.env.ALPACA_API_SECRET!,
    "Content-Type": "application/json",
  };
}

// -- Trading API --

export interface AlpacaAccount {
  equity: string;
  buying_power: string;          // day-trade BP (up to 4x) — NOT the binding constraint
  regt_buying_power: string;     // Reg-T BP (≈2x) — what the broker actually enforces
  non_marginable_buying_power: string;
  cash: string;
  status: string;
}

export interface AlpacaOrder {
  id: string;
  client_order_id: string;
  symbol: string;
  side: "buy" | "sell";
  qty: string;
  filled_qty: string;
  filled_avg_price: string | null;
  status: string;
  type: string;
  submitted_at: string;
  filled_at: string | null;
  legs?: AlpacaOrder[];
}

export async function getAccount(): Promise<AlpacaAccount> {
  const res = await fetch(`${TRADING_URL}/v2/account`, { headers: headers() });
  if (!res.ok) throw new Error(`account ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function getClock(): Promise<{ is_open: boolean; next_open: string; next_close: string }> {
  const res = await fetch(`${TRADING_URL}/v2/clock`, { headers: headers() });
  if (!res.ok) throw new Error(`clock ${res.status}`);
  return res.json();
}

export async function submitBracket(params: {
  symbol: string;
  side: "buy" | "sell";
  qty: number;
  targetPrice: number;
  stopPrice: number;
}): Promise<AlpacaOrder> {
  const body = {
    symbol: params.symbol,
    side: params.side,
    qty: String(params.qty),
    type: "market",
    time_in_force: "day",
    order_class: "bracket",
    take_profit: { limit_price: params.targetPrice.toFixed(2) },
    stop_loss: { stop_price: params.stopPrice.toFixed(2) },
  };
  const res = await fetch(`${TRADING_URL}/v2/orders`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`order ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function getOrder(id: string): Promise<AlpacaOrder> {
  const res = await fetch(`${TRADING_URL}/v2/orders/${id}?nested=true`, { headers: headers() });
  if (!res.ok) throw new Error(`getOrder ${res.status}`);
  return res.json();
}

export async function getClosedOrdersSince(afterISO: string): Promise<AlpacaOrder[]> {
  const params = new URLSearchParams({ status: "closed", after: afterISO, limit: "200", nested: "true" });
  const res = await fetch(`${TRADING_URL}/v2/orders?${params}`, { headers: headers() });
  if (!res.ok) throw new Error(`orders ${res.status}`);
  return res.json();
}

export async function cancelOrder(id: string): Promise<void> {
  await fetch(`${TRADING_URL}/v2/orders/${id}`, { method: "DELETE", headers: headers() });
}

export async function closeAllPositions(): Promise<void> {
  await fetch(`${TRADING_URL}/v2/positions?cancel_orders=true`, {
    method: "DELETE",
    headers: headers(),
  });
}

export async function getPositions(): Promise<{ symbol: string; qty: string }[]> {
  const res = await fetch(`${TRADING_URL}/v2/positions`, { headers: headers() });
  if (!res.ok) return [];
  return res.json();
}

// -- Market data (IEX feed, free tier) --

/** Latest 1-min close for a symbol — the true economic mark for an EOD flatten. */
export async function getLatestClose(symbol: string): Promise<number | null> {
  const start = new Date(Date.now() - 30 * 60000).toISOString();
  const params = new URLSearchParams({
    symbols: symbol, timeframe: "1Min", start, limit: "40", feed: "iex", sort: "asc",
  });
  const res = await fetch(`${ALPACA_REST_URL}/v2/stocks/bars?${params}`, { headers: headers() });
  if (!res.ok) return null;
  const data = await res.json();
  const bars: AlpacaBar[] = data.bars?.[symbol] ?? [];
  return bars.length ? bars[bars.length - 1].c : null;
}

export async function getTodayBars(symbols: string[], startISO: string): Promise<Map<string, AlpacaBar[]>> {
  const out = new Map<string, AlpacaBar[]>();
  const params = new URLSearchParams({
    symbols: symbols.join(","),
    timeframe: "1Min",
    start: startISO,
    limit: "10000",
    feed: "iex",
    sort: "asc",
  });
  const res = await fetch(`${ALPACA_REST_URL}/v2/stocks/bars?${params}`, { headers: headers() });
  if (!res.ok) {
    console.error(`[alpaca] bars ${res.status}: ${(await res.text()).slice(0, 150)}`);
    return out;
  }
  const data = await res.json();
  for (const sym of symbols) {
    out.set(sym, data.bars?.[sym] ?? []);
  }
  return out;
}
