"""Read-only views over the RLVR measurement reports.

The reports are produced by ``scripts/rlvr_measure.py`` and committed under
``evaluation/reports/``. This router only reads them — it never runs the
measurement. Running a measurement from an HTTP handler would make the
reported numbers depend on who last hit the endpoint, and the whole point of
the artifact is that it is reproducible from a commit.

Endpoints:
    GET /api/rlvr/report            latest report, full JSON
    GET /api/rlvr/report/summary    just the headline numbers
    GET /api/rlvr/history           one summary per run, oldest first
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/rlvr", tags=["rlvr"])

# ai-service/api/rlvr.py -> parents[2] == repo root
REPORTS_DIR = Path(__file__).resolve().parents[2] / "evaluation" / "reports"
REPORT_PATH = REPORTS_DIR / "rlvr-measurement.json"
HISTORY_PATH = REPORTS_DIR / "rlvr-measurement-history.jsonl"

_MISSING = (
    "No RLVR measurement has been generated yet. "
    "Run `python3 scripts/rlvr_measure.py` (offline, no API calls)."
)


def _load_report() -> dict:
    if not REPORT_PATH.exists():
        raise HTTPException(status_code=404, detail=_MISSING)
    try:
        return json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500, detail=f"measurement report is not valid JSON: {exc}"
        ) from exc


@router.get("/report")
def rlvr_report() -> dict:
    """The full latest measurement, including per-case candidate scores."""
    return _load_report()


@router.get("/report/summary")
def rlvr_report_summary() -> dict:
    """Headline numbers, the per-distractor breakdown, and the reward itself.

    Carries ``reward_config`` and ``component_analysis`` as well as the rates.
    A summary that reports only aggregates tells you a score moved but not
    which weight, threshold or component moved it — which is the only question
    worth asking of a tracking view.
    """
    report = _load_report()
    return {
        "generated_at": report.get("generated_at"),
        "commit": report.get("commit"),
        "mode": report.get("mode"),
        "case_set_sha256": report.get("case_set_sha256"),
        "summary": report.get("summary", {}),
        "by_kind": report.get("by_kind", {}),
        "reward_config": report.get("reward_config", {}),
        "component_analysis": report.get("component_analysis", {}),
    }


@router.get("/config")
def rlvr_config() -> dict:
    """Just the weights, gates and thresholds behind the latest report."""
    return _load_report().get("reward_config", {})


@router.get("/components")
def rlvr_components() -> dict:
    """Per-component weight, mean values, and measured discrimination."""
    report = _load_report()
    return {
        "generated_at": report.get("generated_at"),
        "commit": report.get("commit"),
        "components": report.get("component_analysis", {}),
    }


@router.get("/case/{case_id}")
def rlvr_case(case_id: str) -> dict:
    """Every candidate for one case, with the full per-component breakdown.

    This is the drill-down: when a headline rate moves, this endpoint shows
    the individual component values that produced each candidate's total.
    """
    report = _load_report()
    for case in report.get("cases", []):
        if case.get("case_id") == case_id:
            return case
    known = [c.get("case_id") for c in report.get("cases", [])]
    raise HTTPException(
        status_code=404,
        detail={"error": f"no case {case_id!r} in the latest report", "known": known},
    )


@router.get("/history")
def rlvr_history(limit: int = 50) -> dict:
    """Run-over-run summaries, so a reward change shows up as a delta."""
    if not HISTORY_PATH.exists():
        raise HTTPException(status_code=404, detail=_MISSING)
    runs = []
    for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            runs.append(json.loads(line))
        except json.JSONDecodeError:
            # A torn line from a killed run should not blank the whole view.
            continue
    trimmed = runs[-limit:] if limit > 0 else runs
    return {"runs": trimmed, "total_runs": len(runs), "returned": len(trimmed)}
