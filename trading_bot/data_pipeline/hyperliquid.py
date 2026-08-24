"""Hyperliquid public market-data client (RESEARCH DATA ONLY).

Uses only the public, unauthenticated info endpoint — no account, no keys,
no order routing. Downloading public candles/funding history for research is
unrelated to the trading restrictions; the live-trading compliance gate lives
in execution/hyperliquid_executor.py and is untouched by this module.

API notes (verified against the public docs; re-verify on first live run):
* POST https://api.hyperliquid.xyz/info  {"type": "candleSnapshot",
    "req": {"coin": "BTC", "interval": "1h", "startTime": ms, "endTime": ms}}
  -> [{"t": open_ms, "T": close_ms, "s": coin, "i": interval, "o": "...",
      "h": "...", "l": "...", "c": "...", "v": "...", "n": trades}, ...]
  At most ~5000 candles per response -> paginate by advancing startTime.
* {"type": "fundingHistory", "coin": "BTC", "startTime": ms, "endTime": ms}
  -> [{"coin", "fundingRate": "...", "premium": "...", "time": ms}, ...]
  Funding is HOURLY; ~500 rows per response -> paginate.

NOTE: this environment may block outbound market-data hosts; in that case
run the fetch CLI from a machine with normal network access.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request

import pandas as pd

from trading_bot.data_pipeline.frames import (
    INTERVALS,
    DataError,
    ensure_canonical,
    interval_to_timedelta,
)
from trading_bot.monitoring.logging import get_logger

log = get_logger("data.hyperliquid")

API_URL = "https://api.hyperliquid.xyz/info"
MAX_CANDLES_PER_REQUEST = 5000
MAX_FUNDING_PER_REQUEST = 500


class HyperliquidDataError(DataError):
    pass


# ---- transport ------------------------------------------------------------------
def _post(payload: dict, *, url: str = API_URL, retries: int = 3, timeout: float = 30.0):
    body = json.dumps(payload).encode()
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "trading-bot-research/0.1"},
                method="POST",
            )
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last_err = e
            status = getattr(e, "code", None)
            if status is not None and 400 <= status < 500 and status != 429:
                break  # a 4xx (other than rate limit) will not heal on retry
            if attempt < retries:
                wait = 2**attempt
                log.warning("Hyperliquid request failed (%s); retry in %ss", e, wait)
                time.sleep(wait)
    raise HyperliquidDataError(
        f"Hyperliquid info request failed after {retries + 1} attempts: {last_err}. "
        "If you are inside a restricted network (this sandbox blocks market-data "
        "hosts), run the fetch from a machine with normal internet access."
    )


# ---- parsing (pure; unit-testable without network) ------------------------------
def parse_candles(raw: list[dict], *, coin: str, interval: str) -> pd.DataFrame:
    """API candle list -> canonical frame (index = bar CLOSE time, UTC)."""
    if interval not in INTERVALS:
        raise HyperliquidDataError(f"unsupported interval {interval!r}")
    if not raw:
        return ensure_canonical(
            pd.DataFrame(columns=["open", "high", "low", "close", "volume"],
                         index=pd.DatetimeIndex([], tz="UTC", name="ts"))
        )
    rows = []
    for c in raw:
        if c.get("s") not in (None, coin):
            raise HyperliquidDataError(f"mixed coins in response: expected {coin}, got {c.get('s')}")
        rows.append(
            {
                # 't' is the bar OPEN in ms; canonical index is the CLOSE time.
                "ts": pd.Timestamp(int(c["t"]), unit="ms", tz="UTC")
                + interval_to_timedelta(interval),
                "open": float(c["o"]),
                "high": float(c["h"]),
                "low": float(c["l"]),
                "close": float(c["c"]),
                "volume": float(c["v"]),
            }
        )
    df = pd.DataFrame(rows).set_index("ts")
    return ensure_canonical(df)


def parse_funding(raw: list[dict], *, coin: str) -> pd.Series:
    """API funding list -> Series of HOURLY funding rates indexed by UTC time.

    Positive rate: longs pay shorts (standard perp convention)."""
    if not raw:
        return pd.Series(dtype="float64", index=pd.DatetimeIndex([], tz="UTC", name="ts"),
                         name="funding_rate")
    idx, vals = [], []
    for r in raw:
        if r.get("coin") not in (None, coin):
            raise HyperliquidDataError(f"mixed coins in funding response for {coin}")
        idx.append(pd.Timestamp(int(r["time"]), unit="ms", tz="UTC"))
        vals.append(float(r["fundingRate"]))
    s = pd.Series(vals, index=pd.DatetimeIndex(idx, name="ts"), name="funding_rate")
    s = s.sort_index()
    return s[~s.index.duplicated(keep="last")]


# ---- fetchers -------------------------------------------------------------------
def fetch_candles(
    coin: str,
    interval: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    url: str = API_URL,
) -> pd.DataFrame:
    """Paginated candle download over [start, end] (tz-aware timestamps)."""
    if start.tz is None or end.tz is None:
        raise HyperliquidDataError("start/end must be tz-aware")
    step_ms = INTERVALS[interval] * 1000
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    frames: list[pd.DataFrame] = []
    cursor = start_ms
    while cursor < end_ms:
        raw = _post(
            {
                "type": "candleSnapshot",
                "req": {"coin": coin, "interval": interval, "startTime": cursor, "endTime": end_ms},
            },
            url=url,
        )
        if not isinstance(raw, list) or not raw:
            break
        frames.append(parse_candles(raw, coin=coin, interval=interval))
        last_open_ms = int(raw[-1]["t"])
        next_cursor = last_open_ms + step_ms
        if next_cursor <= cursor:  # no forward progress -> stop, don't loop forever
            break
        cursor = next_cursor
        if len(raw) < MAX_CANDLES_PER_REQUEST:
            break
        time.sleep(0.25)  # be polite to the public endpoint
    if not frames:
        return parse_candles([], coin=coin, interval=interval)
    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    log.info("fetched %d %s candles for %s (%s .. %s)",
             len(df), interval, coin, df.index[0] if len(df) else "-", df.index[-1] if len(df) else "-")
    return ensure_canonical(df)


def fetch_funding(
    coin: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    url: str = API_URL,
) -> pd.Series:
    """Paginated hourly funding-rate history over [start, end]."""
    if start.tz is None or end.tz is None:
        raise HyperliquidDataError("start/end must be tz-aware")
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    chunks: list[pd.Series] = []
    cursor = start_ms
    while cursor < end_ms:
        raw = _post(
            {"type": "fundingHistory", "coin": coin, "startTime": cursor, "endTime": end_ms},
            url=url,
        )
        if not isinstance(raw, list) or not raw:
            break
        chunks.append(parse_funding(raw, coin=coin))
        last_ms = int(raw[-1]["time"])
        if last_ms + 1 <= cursor:
            break
        cursor = last_ms + 1
        if len(raw) < MAX_FUNDING_PER_REQUEST:
            break
        time.sleep(0.25)
    if not chunks:
        return parse_funding([], coin=coin)
    s = pd.concat(chunks).sort_index()
    return s[~s.index.duplicated(keep="last")]
