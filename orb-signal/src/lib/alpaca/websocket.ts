import WebSocket from "ws";
import { ALPACA_WS_URL, TICKERS } from "../constants";
import type { Bar } from "../types";
import { EventEmitter } from "events";

export class AlpacaWebSocket extends EventEmitter {
  private ws: WebSocket | null = null;
  private connected = false;

  connect(): void {
    this.ws = new WebSocket(ALPACA_WS_URL);

    this.ws.on("open", () => {
      console.log("[ws] Connected to Alpaca");
      this.authenticate();
    });

    this.ws.on("message", (data: WebSocket.Data) => {
      const messages = JSON.parse(data.toString());
      for (const msg of messages) {
        if (msg.T === "success" && msg.msg === "authenticated") {
          console.log("[ws] Authenticated");
          this.connected = true;
          this.subscribe();
          this.emit("ready");
        } else if (msg.T === "b") {
          const bar: Bar = {
            timestamp: new Date(msg.t),
            open: msg.o,
            high: msg.h,
            low: msg.l,
            close: msg.c,
            volume: msg.v,
            symbol: msg.S,
          };
          this.emit("bar", bar);
        } else if (msg.T === "error") {
          console.error("[ws] Error:", msg.msg);
          this.emit("error", new Error(msg.msg));
        }
      }
    });

    this.ws.on("close", () => {
      console.log("[ws] Disconnected");
      this.connected = false;
      this.emit("close");
    });

    this.ws.on("error", (err) => {
      console.error("[ws] WebSocket error:", err.message);
    });
  }

  private authenticate(): void {
    this.ws?.send(JSON.stringify({
      action: "auth",
      key: process.env.ALPACA_API_KEY,
      secret: process.env.ALPACA_API_SECRET,
    }));
  }

  private subscribe(): void {
    this.ws?.send(JSON.stringify({
      action: "subscribe",
      bars: TICKERS,
    }));
    console.log(`[ws] Subscribed to bars: ${TICKERS.join(", ")}`);
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
      this.connected = false;
    }
  }

  isConnected(): boolean {
    return this.connected;
  }
}
