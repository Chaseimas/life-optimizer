"""Feature engineering (Phase 4). Every feature is timestamp-safe.

Convention: the value of a feature at row ``t`` uses ONLY bars up to and
including ``t`` (everything in row ``t`` was known at that bar's close).
Decisions based on row ``t`` execute no earlier than bar ``t+1``'s open —
the backtester enforces that half of the contract.

Every feature here is verified by ``tests/test_features.py`` with the
recompute-on-truncation leak detector (``assert_no_lookahead``). Add a
feature => add it to that test. No exceptions.

Labels (forward returns) are intentionally quarantined in
``make_forward_return_label`` — they contain future information BY DESIGN
and must only ever be used as ML targets, never as features.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_bot.data_pipeline.frames import ensure_canonical


# ---- returns / momentum ---------------------------------------------------------
def log_return(df: pd.DataFrame) -> pd.Series:
    return np.log(df["close"]).diff().rename("log_return")


def momentum(df: pd.DataFrame, n: int) -> pd.Series:
    return df["close"].pct_change(n).rename(f"mom_{n}")


# ---- volatility -----------------------------------------------------------------
def rolling_vol(df: pd.DataFrame, n: int) -> pd.Series:
    return log_return(df).rolling(n).std().rename(f"vol_{n}")


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rename("true_range")


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder's ATR: recursive EMA (adjust=False) — strictly causal."""
    return (
        true_range(df)
        .ewm(alpha=1.0 / n, adjust=False, min_periods=n)
        .mean()
        .rename(f"atr_{n}")
    )


def vol_percentile(df: pd.DataFrame, vol_window: int = 20, rank_window: int = 252) -> pd.Series:
    """Where current realized vol sits within its own recent history (0..1)."""
    v = rolling_vol(df, vol_window)
    return v.rolling(rank_window).rank(pct=True).rename(f"vol_pctile_{vol_window}_{rank_window}")


# ---- volume ---------------------------------------------------------------------
def rel_volume(df: pd.DataFrame, n: int = 20) -> pd.Series:
    med = df["volume"].rolling(n).median()
    return (df["volume"] / med.where(med > 0)).rename(f"rel_vol_{n}")


# ---- location vs. recent range / VWAP -------------------------------------------
def dist_from_rolling_high(df: pd.DataFrame, n: int) -> pd.Series:
    return (df["close"] / df["high"].rolling(n).max() - 1.0).rename(f"dist_high_{n}")


def dist_from_rolling_low(df: pd.DataFrame, n: int) -> pd.Series:
    return (df["close"] / df["low"].rolling(n).min() - 1.0).rename(f"dist_low_{n}")


def rolling_vwap_dist(df: pd.DataFrame, n: int) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = (tp * df["volume"]).rolling(n).sum()
    v = df["volume"].rolling(n).sum()
    vwap = pv / v.where(v > 0)
    return (df["close"] / vwap - 1.0).rename(f"vwap_dist_{n}")


def anchored_vwap_dist(df: pd.DataFrame) -> pd.Series:
    """Distance from the UTC-day-anchored VWAP (cumulative within each day —
    causal). For CME markets the session anchor (Phase 7) will replace the
    UTC-day anchor; for 24/7 perps UTC days are the natural convention."""
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    day = df.index.tz_convert("UTC").date
    pv_cum = (tp * df["volume"]).groupby(day).cumsum()
    v_cum = df["volume"].groupby(day).cumsum()
    vwap = pv_cum / v_cum.where(v_cum > 0)
    return (df["close"] / vwap - 1.0).rename("vwap_dist_day")


# ---- candle structure -----------------------------------------------------------
def candle_body_frac(df: pd.DataFrame) -> pd.Series:
    rng = (df["high"] - df["low"]).where(lambda s: s > 0)
    return ((df["close"] - df["open"]).abs() / rng).rename("body_frac")


def upper_wick_frac(df: pd.DataFrame) -> pd.Series:
    rng = (df["high"] - df["low"]).where(lambda s: s > 0)
    return ((df["high"] - df[["open", "close"]].max(axis=1)) / rng).rename("upper_wick_frac")


def lower_wick_frac(df: pd.DataFrame) -> pd.Series:
    rng = (df["high"] - df["low"]).where(lambda s: s > 0)
    return ((df[["open", "close"]].min(axis=1) - df["low"]) / rng).rename("lower_wick_frac")


# ---- regime ---------------------------------------------------------------------
def efficiency_ratio(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Kaufman efficiency ratio: |net move| / path length over n bars.
    ~1 = clean trend, ~0 = churn. A transparent trend-regime measure."""
    net = df["close"].diff(n).abs()
    path = df["close"].diff().abs().rolling(n).sum()
    return (net / path.where(path > 0)).rename(f"eff_ratio_{n}")


# ---- calendar -------------------------------------------------------------------
def hour_of_day(df: pd.DataFrame) -> pd.Series:
    return pd.Series(df.index.tz_convert("UTC").hour, index=df.index, name="hour_utc").astype(
        "float64"
    )


def day_of_week(df: pd.DataFrame) -> pd.Series:
    return pd.Series(df.index.tz_convert("UTC").dayofweek, index=df.index, name="dow_utc").astype(
        "float64"
    )


# ---- assembly -------------------------------------------------------------------
DEFAULT_FEATURE_PARAMS = {
    "momentum_windows": (5, 20, 60),
    "vol_windows": (20, 60),
    "atr_period": 14,
    "range_windows": (20, 60),
    "vwap_window": 60,
    "rel_volume_window": 20,
    "eff_ratio_window": 20,
    "vol_pctile": (20, 252),
}


def build_features(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    """Assemble the standard feature matrix. Only past-and-present data is
    used at every row; verified by the leak tests."""
    p = {**DEFAULT_FEATURE_PARAMS, **(params or {})}
    df = ensure_canonical(df)
    cols: list[pd.Series] = [log_return(df)]
    for n in p["momentum_windows"]:
        cols.append(momentum(df, n))
    for n in p["vol_windows"]:
        cols.append(rolling_vol(df, n))
    cols.append(atr(df, p["atr_period"]))
    for n in p["range_windows"]:
        cols.append(dist_from_rolling_high(df, n))
        cols.append(dist_from_rolling_low(df, n))
    cols.append(rolling_vwap_dist(df, p["vwap_window"]))
    cols.append(anchored_vwap_dist(df))
    cols.append(rel_volume(df, p["rel_volume_window"]))
    cols.append(candle_body_frac(df))
    cols.append(upper_wick_frac(df))
    cols.append(lower_wick_frac(df))
    cols.append(efficiency_ratio(df, p["eff_ratio_window"]))
    cols.append(vol_percentile(df, *p["vol_pctile"]))
    cols.append(hour_of_day(df))
    cols.append(day_of_week(df))
    return pd.concat(cols, axis=1)


# ---- labels (QUARANTINED: future information by design) -------------------------
def make_forward_return_label(df: pd.DataFrame, horizon: int) -> pd.Series:
    """Forward ``horizon``-bar return, aligned at decision time.

    WARNING: this column contains FUTURE information. It exists solely as an
    ML TARGET. It must never appear in a feature matrix, and the leak tests
    will (correctly) reject it as a feature. The last ``horizon`` rows are
    NaN — there is no future for them; never fill these.
    """
    return (
        df["close"].pct_change(horizon).shift(-horizon).rename(f"label_fwd_ret_{horizon}")
    )
