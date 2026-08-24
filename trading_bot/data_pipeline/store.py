"""Bar storage: parquet files under data/raw and data/processed + sidecar
metadata, so every dataset is identifiable (market, interval, source, span).

Layout (relative to trading_bot/):
    data/raw/<MARKET>_<interval>__<source>.parquet        as-fetched, untouched
    data/processed/<MARKET>_<interval>.parquet            cleaned canonical
    ...and a sidecar .meta.json next to each file.

Raw data is never modified in place — cleaning reads raw, writes processed.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from trading_bot.data_pipeline.frames import DataError, ensure_canonical


def _safe(market_id: str) -> str:
    return market_id.replace(":", "_").replace("/", "_")


@dataclass(frozen=True)
class DatasetMeta:
    market_id: str
    interval: str
    stage: str              # "raw" | "processed"
    source: str             # e.g. "hyperliquid_api", "csv:databento", "synthetic"
    rows: int
    start: str              # ISO close time of first bar
    end: str                # ISO close time of last bar
    written_at: str
    notes: str = ""


class BarStore:
    def __init__(self, raw_dir: str | Path, processed_dir: str | Path):
        self.raw_dir = Path(raw_dir)
        self.processed_dir = Path(processed_dir)

    # ---- paths ---------------------------------------------------------------
    def _path(self, market_id: str, interval: str, stage: str, source: str | None) -> Path:
        if stage == "raw":
            if not source:
                raise DataError("raw datasets require a source label")
            return self.raw_dir / f"{_safe(market_id)}_{interval}__{_safe(source)}.parquet"
        if stage == "processed":
            return self.processed_dir / f"{_safe(market_id)}_{interval}.parquet"
        raise DataError(f"unknown stage {stage!r} (use 'raw' or 'processed')")

    # ---- write ---------------------------------------------------------------
    def save(
        self,
        df: pd.DataFrame,
        *,
        market_id: str,
        interval: str,
        stage: str,
        source: str,
        notes: str = "",
    ) -> Path:
        df = ensure_canonical(df)
        if df.empty:
            raise DataError("refusing to save an empty dataset")
        path = self._path(market_id, interval, stage, source)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path)
        meta = DatasetMeta(
            market_id=market_id,
            interval=interval,
            stage=stage,
            source=source,
            rows=len(df),
            start=df.index[0].isoformat(),
            end=df.index[-1].isoformat(),
            written_at=datetime.now(timezone.utc).isoformat(),
            notes=notes,
        )
        path.with_suffix(".meta.json").write_text(json.dumps(asdict(meta), indent=2))
        return path

    # ---- read ----------------------------------------------------------------
    def load(
        self, market_id: str, interval: str, stage: str = "processed", source: str | None = None
    ) -> pd.DataFrame:
        path = self._path(market_id, interval, stage, source)
        if not path.exists():
            raise FileNotFoundError(
                f"No {stage} dataset for {market_id} @ {interval} at {path}. "
                "Fetch/import data first: see `python -m trading_bot.data_pipeline.fetch --help`."
            )
        return ensure_canonical(pd.read_parquet(path))

    def meta(self, market_id: str, interval: str, stage: str = "processed",
             source: str | None = None) -> dict:
        p = self._path(market_id, interval, stage, source).with_suffix(".meta.json")
        return json.loads(p.read_text()) if p.exists() else {}

    # ---- funding (perps) -----------------------------------------------------
    def save_funding(self, s: pd.Series, market_id: str) -> Path:
        if s.index.tz is None:
            raise DataError("funding series index must be tz-aware")
        path = self.raw_dir / f"{_safe(market_id)}__funding.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame = s.rename("funding_rate").to_frame()
        frame.index.name = "ts"
        frame.to_parquet(path)
        return path

    def load_funding(self, market_id: str) -> pd.Series:
        path = self.raw_dir / f"{_safe(market_id)}__funding.parquet"
        if not path.exists():
            raise FileNotFoundError(f"No funding history stored for {market_id} at {path}")
        s = pd.read_parquet(path)["funding_rate"]
        return s.sort_index()

    # ---- catalog -------------------------------------------------------------
    def catalog(self) -> list[dict]:
        """Everything stored, from the sidecar metadata files."""
        entries = []
        for d in (self.raw_dir, self.processed_dir):
            if not d.exists():
                continue
            for meta_path in sorted(d.glob("*.meta.json")):
                try:
                    entries.append(json.loads(meta_path.read_text()))
                except json.JSONDecodeError:
                    entries.append({"error": f"corrupt metadata: {meta_path}"})
        return entries
