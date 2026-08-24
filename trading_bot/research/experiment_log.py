"""Experiment tracking: append-only JSONL log of every experiment ever run.

Rules:
* EVERY experiment gets logged — the losers especially. Cherry-picking the
  best of N runs and forgetting N-1 is how overfitting hides; the log is the
  denominator for any multiple-testing honesty later.
* Append-only: records are never edited or deleted by code.
* Each record captures: id, timestamp, strategy, market, params, dataset,
  train/validation/test periods, results, notes, git revision.
"""

from __future__ import annotations

import json
import secrets
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from trading_bot.monitoring.logging import get_logger

log = get_logger("experiment_log")


def _git_revision() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=Path(__file__).resolve().parent,
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    created_at: str            # ISO-8601 UTC
    strategy: str
    market: str
    params: dict
    dataset: str               # description/hash of the data used
    train_period: str | None = None
    validation_period: str | None = None
    test_period: str | None = None
    results: dict = field(default_factory=dict)
    notes: str = ""
    code_version: str = "unknown"


class ExperimentLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        *,
        strategy: str,
        market: str,
        params: dict,
        dataset: str,
        results: dict,
        train_period: str | None = None,
        validation_period: str | None = None,
        test_period: str | None = None,
        notes: str = "",
    ) -> ExperimentRecord:
        now = datetime.now(timezone.utc)
        record = ExperimentRecord(
            experiment_id=f"exp_{now:%Y%m%dT%H%M%S}_{secrets.token_hex(3)}",
            created_at=now.isoformat(),
            strategy=strategy,
            market=market,
            params=dict(params),
            dataset=dataset,
            train_period=train_period,
            validation_period=validation_period,
            test_period=test_period,
            results=dict(results),
            notes=notes,
            code_version=_git_revision(),
        )
        line = json.dumps(asdict(record), default=str, sort_keys=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
        log.info("logged experiment %s (%s on %s)", record.experiment_id, strategy, market)
        return record

    def load_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        records = []
        with open(self.path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    log.error("corrupt experiment record at %s:%d (kept file intact)",
                              self.path, lineno)
        return records

    def count(self, strategy: str | None = None) -> int:
        records = self.load_all()
        if strategy is None:
            return len(records)
        return sum(1 for r in records if r.get("strategy") == strategy)
