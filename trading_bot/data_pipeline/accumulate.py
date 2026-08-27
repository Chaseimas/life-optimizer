"""Out-of-sample data accumulation (Pass 3).

The public Hyperliquid API only retains ~5,000 candles per interval, so
history beyond that window exists only if WE keep it. This module merges each
new fetch into the stored raw dataset under strict rules:

* EXISTING ROWS ARE IMMUTABLE. A previously stored bar is never modified or
  deleted, even if the API now returns different values for it — such
  overlap mismatches are DETECTED and REPORTED (API revision / venue change),
  and the original stored value is kept. History is written once.
* Only rows with genuinely new timestamps are appended.
* Every fetch appends an entry to the dataset's ``fetch_history`` metadata:
  when it ran, what span it requested, how many rows were new/overlapping/
  mismatched, and the coverage range after the merge. The audit trail of how
  a dataset grew is part of the dataset.
* Anomaly detection on the merged result: duplicate timestamps inside the
  fetch, bars off the interval grid (timestamp discontinuities), and gaps
  (missing candles — reported, NEVER filled).
* The processed dataset is regenerated from the full merged raw data through
  the standard cleaning pass. Contamination protection for completed
  experiments is by TIMESTAMP BOUNDARY (a frozen candidate's ``oos_start``),
  which immutability of old rows makes trustworthy — see
  tests/test_accumulate.py for the proof-by-test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from trading_bot.data_pipeline.clean import clean_frame
from trading_bot.data_pipeline.frames import INTERVALS, ensure_canonical
from trading_bot.data_pipeline.store import BarStore
from trading_bot.monitoring.logging import get_logger

log = get_logger("data.accumulate")

RAW_SOURCE = "hyperliquid_api"
PRICE_TOL = 1e-9  # relative tolerance for overlap comparison


@dataclass
class AccumulationReport:
    market_id: str
    interval: str
    fetched_rows: int = 0
    prior_rows: int = 0
    new_rows: int = 0
    overlap_rows: int = 0
    overlap_mismatches: int = 0          # API returned different values for stored bars
    mismatch_samples: list = field(default_factory=list)
    dupes_in_fetch: int = 0
    off_grid_rows: int = 0               # timestamps not on the interval grid
    gaps: int = 0
    missing_bars: int = 0
    total_rows: int = 0
    coverage_start: str = ""
    coverage_end: str = ""
    funding_new_rows: int | None = None
    funding_mismatches: int | None = None

    def summary(self) -> str:
        return (
            f"{self.market_id}@{self.interval}: fetched={self.fetched_rows} "
            f"prior={self.prior_rows} new={self.new_rows} overlap={self.overlap_rows} "
            f"MISMATCHES={self.overlap_mismatches} dupes={self.dupes_in_fetch} "
            f"off_grid={self.off_grid_rows} gaps={self.gaps} "
            f"missing={self.missing_bars} total={self.total_rows}"
        )


def _fetch_event(report: AccumulationReport, requested_span: tuple[str, str]) -> dict:
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "requested_span": list(requested_span),
        "fetched_rows": report.fetched_rows,
        "new_rows": report.new_rows,
        "overlap_rows": report.overlap_rows,
        "overlap_mismatches": report.overlap_mismatches,
        "rows_after_merge": report.total_rows,
        "coverage": [report.coverage_start, report.coverage_end],
    }


def merge_immutable(old: pd.DataFrame, new: pd.DataFrame,
                    report: AccumulationReport) -> pd.DataFrame:
    """old ∪ new with old rows immutable; mismatched overlaps detected."""
    new = ensure_canonical(new)
    if old.empty:
        report.new_rows = len(new)
        return new
    old = ensure_canonical(old)

    overlap_idx = old.index.intersection(new.index)
    report.overlap_rows = len(overlap_idx)
    if len(overlap_idx):
        a = old.loc[overlap_idx].to_numpy(dtype=float)
        b = new.loc[overlap_idx].to_numpy(dtype=float)
        row_mismatch = ~np.all(np.isclose(a, b, rtol=PRICE_TOL, equal_nan=True), axis=1)
        report.overlap_mismatches = int(row_mismatch.sum())
        if report.overlap_mismatches:
            for ts in overlap_idx[row_mismatch][:5]:
                report.mismatch_samples.append({
                    "ts": ts.isoformat(),
                    "stored": old.loc[ts].to_dict(),
                    "api_now": new.loc[ts].to_dict(),
                })
            log.warning(
                "%s@%s: API returned %d bars differing from stored history — "
                "stored values KEPT, discrepancy logged",
                report.market_id, report.interval, report.overlap_mismatches,
            )
    fresh = new.loc[~new.index.isin(old.index)]
    report.new_rows = len(fresh)
    merged = pd.concat([old, fresh]).sort_index()
    return ensure_canonical(merged, already_sorted=True)


def _detect_anomalies(df: pd.DataFrame, interval: str, report: AccumulationReport) -> None:
    step = INTERVALS[interval]
    # Unit-agnostic epoch seconds (pandas may store datetimes in us or ns):
    epoch_seconds = (df.index - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1)
    report.off_grid_rows = int((epoch_seconds.to_numpy() % step != 0).sum())
    diffs = df.index.to_series().diff().dropna().dt.total_seconds()
    gap_mask = diffs > step
    report.gaps = int(gap_mask.sum())
    report.missing_bars = int(((diffs[gap_mask] / step) - 1).sum()) if report.gaps else 0


def accumulate_candles(
    store: BarStore,
    market_id: str,
    coin: str,
    interval: str,
    *,
    days: int,
    fetch_fn=None,
    funding_fetch_fn=None,
    now: pd.Timestamp | None = None,
) -> AccumulationReport:
    """Fetch recent candles and merge them into stored history (append-only)."""
    if fetch_fn is None:
        from trading_bot.data_pipeline.hyperliquid import fetch_candles
        fetch_fn = fetch_candles
    now = now or pd.Timestamp.now(tz="UTC")
    start = now - pd.Timedelta(days=days)
    report = AccumulationReport(market_id=market_id, interval=interval)

    new = fetch_fn(coin, interval, start, now)
    report.fetched_rows = len(new)
    report.dupes_in_fetch = int(new.index.duplicated().sum()) if len(new) else 0

    try:
        old = store.load(market_id, interval, stage="raw", source=RAW_SOURCE)
    except FileNotFoundError:
        old = pd.DataFrame(columns=["open", "high", "low", "close", "volume"],
                           index=pd.DatetimeIndex([], tz="UTC", name="ts"))
    report.prior_rows = len(old)

    if len(new) == 0 and len(old) == 0:
        raise ValueError(f"no data fetched and none stored for {market_id}@{interval}")

    merged = merge_immutable(old, new, report) if len(new) else old
    _detect_anomalies(merged, interval, report)
    report.total_rows = len(merged)
    report.coverage_start = merged.index[0].isoformat()
    report.coverage_end = merged.index[-1].isoformat()

    prior_meta = store.meta(market_id, interval, stage="raw", source=RAW_SOURCE)
    history = list(prior_meta.get("fetch_history", []))
    history.append(_fetch_event(report, (start.isoformat(), now.isoformat())))

    store.save(merged, market_id=market_id, interval=interval, stage="raw",
               source=RAW_SOURCE, notes="accumulated (append-only; old rows immutable)",
               extra_meta={"fetch_history": history})

    clean, clean_rep = clean_frame(merged, interval=interval, is_24_7=True)
    store.save(clean, market_id=market_id, interval=interval, stage="processed",
               source=RAW_SOURCE, notes=f"cleaned from accumulated raw: {clean_rep.summary()}",
               extra_meta={"fetch_history": history})

    # ---- funding (hourly series, same immutability rule) ---------------------
    if funding_fetch_fn is not None:
        new_f = funding_fetch_fn(coin, start, now)
        try:
            old_f = store.load_funding(market_id)
        except FileNotFoundError:
            old_f = pd.Series(dtype="float64",
                              index=pd.DatetimeIndex([], tz="UTC", name="ts"))
        overlap = old_f.index.intersection(new_f.index)
        mism = int((~np.isclose(old_f.loc[overlap], new_f.loc[overlap],
                                rtol=PRICE_TOL)).sum()) if len(overlap) else 0
        fresh_f = new_f.loc[~new_f.index.isin(old_f.index)]
        merged_f = pd.concat([old_f, fresh_f]).sort_index()
        store.save_funding(merged_f, market_id)
        report.funding_new_rows = len(fresh_f)
        report.funding_mismatches = mism

    log.info("accumulated %s", report.summary())
    return report
