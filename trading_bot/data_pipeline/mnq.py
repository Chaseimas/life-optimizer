"""MNQ (CME Micro E-mini Nasdaq-100) data pipeline — Pass 3 groundwork.

SCOPE, deliberately narrow: this module establishes the DATA path for MNQ —
import, schema, timezone/session handling, tick validation, cost assumptions
— so that when Databento history is purchased, research can start on a
validated pipeline instead of improvising one. NO MNQ strategy is optimized
or evaluated here, and the MNQ track stays completely separate from the
frozen crypto candidate.

Data source: Databento OHLCV CSV exports (``ts_event`` nanosecond epoch UTC,
bar-open semantics) — the defaults of ``csv_import.ColumnMap``. For
continuous history either use Databento's continuous symbology or stitch
per-contract files with ``data_pipeline/continuous.py`` (volume-roll,
difference-adjusted; both are tested).

Transaction-cost assumptions (documented, not hidden — VERIFY against your
broker before trusting any MNQ result): see ``MNQ_COST_ASSUMPTIONS``. The
fee lives in the market spec / config (``venues.cme.fees``), never in
strategy logic.

Session handling: CME Globex hours via ``clean.filter_cme_session``
(DST-aware, America/Chicago). Opening ranges for U.S. futures must anchor to
the exchange session open — ``rth_opening_range`` below computes
session-anchored ranges in exchange-local time. It is a SUPPORT UTILITY for
future exploratory MNQ strategies; it is not wired into any strategy and has
no bearing on the frozen candidate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from trading_bot.data_pipeline.clean import clean_frame, filter_cme_session
from trading_bot.data_pipeline.csv_import import ColumnMap, import_csv
from trading_bot.data_pipeline.store import BarStore
from trading_bot.monitoring.logging import get_logger

log = get_logger("data.mnq")

MNQ_TICK = 0.25

MNQ_COST_ASSUMPTIONS = {
    "commission_per_side_usd": 1.24,   # all-in default from config venues.cme.fees
    "slippage_assumption": "1 tick ($0.50 per contract per side), taker",
    "tick_size": MNQ_TICK,
    "point_value_usd": 2.0,
    "verification_required": (
        "Broker commission schedules vary; VERIFY before drawing any MNQ "
        "conclusion. Maker (limit) execution on CME has different queue "
        "dynamics than crypto perps — the maker fill model's assumptions "
        "must be revisited for MNQ, not blindly reused."
    ),
}


@dataclass
class MNQImportReport:
    source_file: str = ""
    rows_imported: int = 0
    off_tick_prices: int = 0           # price fields not on the 0.25 grid
    session_rows_dropped: int = 0
    rows_processed: int = 0
    clean_summary: str = ""
    coverage_start: str = ""
    coverage_end: str = ""
    notes: list = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"MNQ import {self.source_file}: in={self.rows_imported} "
            f"off_tick={self.off_tick_prices} session_dropped={self.session_rows_dropped} "
            f"out={self.rows_processed} span={self.coverage_start}..{self.coverage_end}"
        )


def count_off_tick(df: pd.DataFrame, tick: float = MNQ_TICK) -> int:
    """Price fields that do not sit on the tick grid (data-quality signal)."""
    prices = df[["open", "high", "low", "close"]].to_numpy(dtype=float)
    remainder = np.abs(np.round(prices / tick) * tick - prices)
    return int((remainder > tick * 1e-6).sum())


def import_mnq_csv(
    store: BarStore,
    path: str | Path,
    *,
    interval: str,
    colmap: ColumnMap | None = None,
    holidays: list[date] | None = None,
) -> MNQImportReport:
    """Import a Databento-shaped MNQ CSV: raw stored untouched, session
    filter + cleaning applied, everything counted in the report."""
    path = Path(path)
    colmap = colmap or ColumnMap(interval=interval)
    report = MNQImportReport(source_file=path.name)

    df = import_csv(path, colmap)
    report.rows_imported = len(df)
    report.off_tick_prices = count_off_tick(df)
    if report.off_tick_prices:
        report.notes.append(
            f"{report.off_tick_prices} price fields off the {MNQ_TICK} tick grid — "
            "check the export's price scale/precision"
        )

    store.save(df, market_id="MNQ", interval=interval, stage="raw",
               source=f"csv:{path.name}",
               notes=f"MNQ raw import; costs assumed: {MNQ_COST_ASSUMPTIONS['commission_per_side_usd']}/side")

    in_session, srep = filter_cme_session(df, holidays=holidays)
    report.session_rows_dropped = srep.session_rows_dropped
    clean, crep = clean_frame(in_session, interval=interval, is_24_7=False)
    report.clean_summary = crep.summary()
    report.rows_processed = len(clean)
    if len(clean):
        report.coverage_start = clean.index[0].isoformat()
        report.coverage_end = clean.index[-1].isoformat()
    store.save(clean, market_id="MNQ", interval=interval, stage="processed",
               source=f"csv:{path.name}",
               notes=f"session-filtered + cleaned: {report.clean_summary}")
    log.info(report.summary())
    return report


def rth_opening_range(
    df: pd.DataFrame,
    *,
    range_minutes: int = 30,
    session_open: str = "08:30",
    tz: str = "America/Chicago",
) -> pd.DataFrame:
    """Session-anchored opening ranges, one row per exchange-local trading day.

    EXPLORATORY SUPPORT UTILITY — not wired into any strategy; kept separate
    from the frozen crypto candidate.

    Anchored at ``session_open`` exchange-local time (DST-aware: 08:30 CT is
    14:30 UTC in winter and 13:30 UTC in summer — this handles both). A bar
    contributes if its CLOSE time falls in (open, open + range_minutes].
    Leak-safety contract for future consumers: a row's values are fully known
    at its ``range_end_ts`` and may only be used at or after that moment.
    """
    open_h, open_m = (int(x) for x in session_open.split(":"))
    open_minutes = open_h * 60 + open_m
    local = df.index.tz_convert(tz)
    minutes = local.hour * 60 + local.minute
    in_range = (minutes > open_minutes) & (minutes <= open_minutes + range_minutes)
    sub = df[in_range]
    if sub.empty:
        return pd.DataFrame(columns=["range_high", "range_low", "n_bars", "range_end_ts"])
    session_day = pd.Series(sub.index.tz_convert(tz).date, index=sub.index)
    grouped = sub.groupby(session_day.to_numpy())
    out = pd.DataFrame({
        "range_high": grouped["high"].max(),
        "range_low": grouped["low"].min(),
        "n_bars": grouped["close"].count(),
    })
    out["range_end_ts"] = pd.Series(sub.index, index=sub.index).groupby(
        session_day.to_numpy()
    ).max()
    out.index.name = "session_date"
    return out
