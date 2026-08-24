"""Data cleaning (Phase 3): raw frames in, audited canonical frames out.

Principles:
* Cleaning DROPS or FLAGS data; it never fabricates bars or fills gaps with
  synthetic prices. A gap stays a gap and is reported.
* Every action is counted in a ``CleanReport`` so datasets are auditable.
* Cleaning is offline preprocessing and may inspect neighboring bars (e.g.
  the classic bad-tick signature "huge move, immediately fully reverted").
  This is not a trading decision, so it is not look-ahead in the research
  sense — but it only ever REMOVES rows; it never creates values.

Session handling: 24/7 markets (perps) get strict gap accounting. For CME
markets, ``filter_cme_session`` removes the daily maintenance halt, weekends
and (optionally) holidays BEFORE gap accounting, using exchange-local time
(America/Chicago, DST-aware).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from trading_bot.data_pipeline.frames import ensure_canonical, interval_to_timedelta


@dataclass
class CleanReport:
    rows_in: int = 0
    rows_out: int = 0
    duplicates_dropped: int = 0
    nan_dropped: int = 0
    nonpositive_dropped: int = 0
    incoherent_dropped: int = 0
    bad_ticks_dropped: int = 0
    extreme_moves_flagged: int = 0    # kept in the data, listed here for review
    gap_count: int = 0
    gap_bars_missing: int = 0
    largest_gap: str = ""
    session_rows_dropped: int = 0
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"in={self.rows_in} out={self.rows_out} dup={self.duplicates_dropped} "
            f"nan={self.nan_dropped} nonpos={self.nonpositive_dropped} "
            f"incoherent={self.incoherent_dropped} bad_ticks={self.bad_ticks_dropped} "
            f"flagged={self.extreme_moves_flagged} gaps={self.gap_count} "
            f"missing_bars={self.gap_bars_missing} session_dropped={self.session_rows_dropped}"
        )


# Interval-aware floor for what counts as an "extreme" single-bar move.
_EXTREME_RETURN_FLOOR = {
    "1m": 0.01, "5m": 0.02, "15m": 0.03, "30m": 0.04, "1h": 0.05, "4h": 0.08, "1d": 0.15,
}


def clean_frame(
    df: pd.DataFrame,
    *,
    interval: str,
    is_24_7: bool = True,
    drop_bad_ticks: bool = True,
    mad_multiplier: float = 12.0,
    report: CleanReport | None = None,
) -> tuple[pd.DataFrame, CleanReport]:
    """Full cleaning pass. Returns (clean frame, audit report)."""
    rep = report or CleanReport()
    rep.rows_in = len(df)

    # --- shape: sorted unique tz-aware UTC index ------------------------------
    dupes_before = int(df.index.duplicated().sum()) if isinstance(df.index, pd.DatetimeIndex) else 0
    out = ensure_canonical(df)
    rep.duplicates_dropped = dupes_before

    # --- hard-invalid rows ----------------------------------------------------
    nan_mask = out[["open", "high", "low", "close"]].isna().any(axis=1) | out["volume"].isna()
    rep.nan_dropped = int(nan_mask.sum())
    out = out[~nan_mask]

    nonpos = (out[["open", "high", "low", "close"]] <= 0).any(axis=1) | (out["volume"] < 0)
    rep.nonpositive_dropped = int(nonpos.sum())
    out = out[~nonpos]

    incoherent = (
        (out["high"] < out["low"])
        | (out["high"] < out[["open", "close"]].max(axis=1))
        | (out["low"] > out[["open", "close"]].min(axis=1))
    )
    rep.incoherent_dropped = int(incoherent.sum())
    out = out[~incoherent]

    # --- bad ticks / extreme moves -------------------------------------------
    if len(out) > 30:
        r = np.log(out["close"]).diff()
        scale = r.abs().rolling(200, min_periods=20).median() * 1.4826
        floor = _EXTREME_RETURN_FLOOR.get(interval, 0.05)
        threshold = np.maximum(mad_multiplier * scale, floor)
        extreme = r.abs() > threshold

        # Bad-tick signature: extreme move that the NEXT bar almost fully
        # reverts. Those rows are dropped (venue glitch, not a market move).
        next_r = r.shift(-1)
        reverted = extreme & ((r + next_r).abs() < 0.25 * r.abs())
        if drop_bad_ticks:
            rep.bad_ticks_dropped = int(reverted.sum())
            out = out[~reverted.reindex(out.index, fill_value=False)]
            extreme = extreme & ~reverted
        # Real but extreme moves are KEPT (crashes are data, not errors) and
        # flagged for eyeballing.
        rep.extreme_moves_flagged = int(extreme.sum())
        if rep.extreme_moves_flagged:
            worst = r.abs().idxmax()
            rep.notes.append(f"largest single-bar |log return| at {worst}")

    # --- gap accounting (never filled, only reported) -------------------------
    if len(out) > 1:
        step = interval_to_timedelta(interval)
        diffs = out.index.to_series().diff().dropna()
        if is_24_7:
            gaps = diffs[diffs > step]
        else:
            # Session markets: only flag suspicious in-session gaps; session
            # breaks should be removed by filter_cme_session before cleaning.
            gaps = diffs[diffs > 3 * step]
            if not gaps.empty:
                rep.notes.append(
                    "session market: gap accounting is approximate — apply the "
                    "session filter before cleaning for exact accounting"
                )
        rep.gap_count = int(len(gaps))
        rep.gap_bars_missing = int(((gaps / step) - 1).sum())
        if len(gaps):
            worst_end = gaps.idxmax()
            rep.largest_gap = f"{gaps.max()} ending {worst_end}"

    rep.rows_out = len(out)
    return out, rep


def filter_cme_session(
    df: pd.DataFrame,
    *,
    holidays: list[date] | None = None,
    report: CleanReport | None = None,
) -> tuple[pd.DataFrame, CleanReport]:
    """Keep only bars inside CME Globex hours (DST-aware, America/Chicago).

    Globex: Sun 17:00 CT -> Fri 16:00 CT, daily halt 16:00-17:00 CT.
    Bar timestamps are CLOSE times: a bar closing at exactly 16:00 CT is the
    last in-session bar; one closing at 17:00 CT sits in the halt.
    Holidays (full-day closures / early closes) are passed explicitly — an
    embedded holiday calendar would silently go stale.
    """
    rep = report or CleanReport()
    out = ensure_canonical(df)
    rows_before = len(out)

    ct = out.index.tz_convert("America/Chicago")
    minutes = ct.hour * 60 + ct.minute  # close-time minutes since midnight CT
    dow = ct.dayofweek  # Mon=0 .. Sun=6

    open_minute = 17 * 60   # 17:00 CT
    close_minute = 16 * 60  # 16:00 CT

    in_week = dow <= 4  # Mon-Fri full days (rules below carve the edges)
    monfri_session = in_week & ((minutes > open_minute) | (minutes <= close_minute))
    # Friday evening (after 17:00 CT) is closed for the week:
    friday_evening = (dow == 4) & (minutes > open_minute)
    # Sunday opens at 17:00 CT:
    sunday_session = (dow == 6) & (minutes > open_minute)

    keep = (monfri_session & ~friday_evening) | sunday_session
    if holidays:
        holiday_mask = pd.Series(ct.date, index=out.index).isin(set(holidays)).to_numpy()
        keep = keep & ~holiday_mask

    out = out[keep]
    rep.session_rows_dropped += rows_before - len(out)
    rep.rows_out = len(out)
    return out, rep
