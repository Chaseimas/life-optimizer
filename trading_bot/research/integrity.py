"""Automated research-integrity checks (Pass 3).

What is enforced WHERE — one map, so nothing is assumed covered twice:

* Look-ahead / future-data leakage .... models/validation.assert_no_lookahead
  (feature-level), strategy truncation-invariance tests, engine
  truncation-invariance test, walk-forward warmup gating + in-run leak
  asserts, frozen_eval's entry-timestamp assert. Enforced by the test suite.
* Old data immutability ............... data_pipeline/accumulate (old rows
  never modified; proven by tests/test_accumulate.py).
* Frozen definition drift ............. hash checks HERE (candidate JSON +
  pinned source files), expected values in frozen_hashes.json AND the tests.
* Parameter tuning on OOS data ........ experiment-log audit HERE: any
  experiment on a frozen candidate's market+interval+strategy after the
  freeze whose parameters differ from the frozen set is flagged, unless its
  notes explicitly label it "exploratory".
* OOS reuse as training ............... structural: frozen_eval slices
  strictly after oos_start and refuses parameters entirely; peeks are logged.
* Survivorship / selection bias ....... the experiment log is append-only and
  keeps every loser; the audit reports per-strategy counts so quiet
  disappearance of losers is visible.
* Gross P&L without costs ............. audit flags pass-3+/frozen records
  whose results carry no execution/fee information.
* Paper fills treated as real ......... every paper artifact is stamped
  mode=PAPER (tested); the audit scans paper_runs for missing stamps.

Run:  python -m trading_bot.research.integrity
Exit code 1 on any VIOLATION.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from trading_bot.research import frozen as frozen_mod
from trading_bot.research.experiment_log import ExperimentLog


@dataclass(frozen=True)
class Finding:
    severity: str            # "VIOLATION" | "WARNING" | "OK"
    check: str
    detail: str


def check_frozen_hashes() -> list[Finding]:
    findings: list[Finding] = []
    try:
        expected = frozen_mod.expected_hashes()
    except FileNotFoundError:
        return [Finding("VIOLATION", "frozen_hashes",
                        f"missing {frozen_mod.HASHES_PATH}")]
    for name in frozen_mod.FROZEN_CANDIDATES:
        want = expected.get("candidates", {}).get(name)
        got = frozen_mod.definition_hash(name)
        if want is None:
            findings.append(Finding("VIOLATION", "frozen_hashes",
                                    f"candidate {name} has no registered hash"))
        elif want != got:
            findings.append(Finding(
                "VIOLATION", "frozen_hashes",
                f"candidate {name} definition CHANGED since freeze "
                f"(expected {want[:12]}…, got {got[:12]}…)"))
        else:
            findings.append(Finding("OK", "frozen_hashes", f"candidate {name} intact"))
    for rel, want in expected.get("source_files", {}).items():
        got = frozen_mod.source_file_hash(rel)
        if want != got:
            findings.append(Finding(
                "VIOLATION", "frozen_hashes",
                f"pinned source file {rel} CHANGED since freeze — frozen "
                "evaluations are void until the freeze is explicitly renewed"))
        else:
            findings.append(Finding("OK", "frozen_hashes", f"{rel} intact"))
    return findings


def audit_experiment_log(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    records = ExperimentLog(path).load_all()
    if not records:
        return [Finding("WARNING", "experiment_log", "no experiment records found")]

    ids = [r.get("experiment_id") for r in records]
    if len(ids) != len(set(ids)):
        findings.append(Finding("VIOLATION", "experiment_log",
                                "duplicate experiment ids — log may have been edited"))
    else:
        findings.append(Finding("OK", "experiment_log",
                                f"{len(records)} records, ids unique (losers preserved)"))

    per_strategy: dict[str, int] = {}
    for r in records:
        per_strategy[r.get("strategy", "?")] = per_strategy.get(r.get("strategy", "?"), 0) + 1
    findings.append(Finding("OK", "selection_bias",
                            f"experiments per strategy (denominator): {per_strategy}"))

    # Tuning-on-OOS detection per frozen candidate:
    for name, frozen in frozen_mod.FROZEN_CANDIDATES.items():
        frozen_at = frozen["frozen_at"]
        tuned = []
        for r in records:
            if r.get("strategy") != frozen["strategy"]:
                continue
            if r.get("market") != frozen["market"]:
                continue
            if frozen["interval"] not in str(r.get("dataset", "")):
                continue
            if str(r.get("created_at", ""))[:10] <= frozen_at:
                continue  # pre-freeze research is in-sample history, fine
            notes = str(r.get("notes", "")).lower()
            if "exploratory" in notes:
                continue  # explicitly labeled exploratory work is allowed
            params = r.get("params", {})
            core = {k: params.get(k) for k in frozen["params"] if k in params}
            if ("grid" in params) or (core and core != frozen["params"]):
                tuned.append(r.get("experiment_id"))
        if tuned:
            findings.append(Finding(
                "VIOLATION", "oos_tuning",
                f"{name}: {len(tuned)} post-freeze experiments with non-frozen "
                f"parameters on the candidate's market/interval (ids {tuned[:5]}) — "
                "parameter tuning on OOS data, or unlabeled exploratory work"))
        else:
            findings.append(Finding("OK", "oos_tuning",
                                    f"{name}: no post-freeze parameter drift detected"))

        peeks = [r for r in records
                 if "frozen_oos_evaluation" in str(r.get("notes", ""))
                 and "peek" in str(r.get("notes", "")).lower()]
        if peeks:
            findings.append(Finding(
                "WARNING", "early_peeks",
                f"{len(peeks)} early peek(s) at the OOS window are on record — "
                "each peek weakens the pre-registered evaluation"))

    # Cost transparency for pass-3+/frozen records:
    opaque = []
    for r in records:
        notes = str(r.get("notes", ""))
        if not ("pass3" in notes or "frozen_oos_evaluation" in notes):
            continue
        res_json = json.dumps(r.get("results", {}))
        if "NO OOS DATA" in res_json:
            continue  # nothing executed -> no execution costs exist to report
        has_costs = any(k in res_json for k in
                        ("execution_model", "execution_assumptions", "fees"))
        if not has_costs:
            opaque.append(r.get("experiment_id"))
    if opaque:
        findings.append(Finding(
            "VIOLATION", "cost_transparency",
            f"{len(opaque)} pass-3/frozen records report results without "
            f"execution/fee information (ids {opaque[:5]})"))
    else:
        findings.append(Finding("OK", "cost_transparency",
                                "pass-3/frozen records carry execution costs"))
    return findings


def audit_paper_runs(paper_root: Path) -> list[Finding]:
    if not paper_root.exists():
        return [Finding("OK", "paper_labeling", "no paper runs recorded yet")]
    findings: list[Finding] = []
    unlabeled = []
    for run_dir in sorted(p for p in paper_root.iterdir() if p.is_dir()):
        for fname in ("result.json", "state.json"):
            f = run_dir / fname
            if f.exists():
                try:
                    if json.loads(f.read_text()).get("mode") != "PAPER":
                        unlabeled.append(f"{run_dir.name}/{fname}")
                except json.JSONDecodeError:
                    unlabeled.append(f"{run_dir.name}/{fname} (corrupt)")
    if unlabeled:
        findings.append(Finding(
            "VIOLATION", "paper_labeling",
            f"paper artifacts missing the PAPER stamp: {unlabeled[:5]} — "
            "simulated fills must never be presentable as real fills"))
    else:
        findings.append(Finding("OK", "paper_labeling",
                                "all paper artifacts stamped mode=PAPER"))
    return findings


def run_all(config) -> tuple[list[Finding], bool]:
    findings = []
    findings += check_frozen_hashes()
    findings += audit_experiment_log(config.resolve(config.research.experiment_log))
    findings += audit_paper_runs(config.root / "paper_runs")
    ok = not any(f.severity == "VIOLATION" for f in findings)
    return findings, ok


def main(argv: list[str] | None = None) -> int:
    from trading_bot.core.config import load_config
    from trading_bot.monitoring.logging import setup_logging

    config = load_config()
    setup_logging(config, console=False)
    findings, ok = run_all(config)
    print("=" * 72)
    print("RESEARCH INTEGRITY REPORT")
    print("=" * 72)
    for f in findings:
        print(f"[{f.severity:9s}] {f.check:18s} {f.detail}")
    print("=" * 72)
    print("RESULT:", "CLEAN" if ok else "VIOLATIONS FOUND — investigate before "
                                        "trusting any recent research output")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
