"""Read-only views over the RLVR measurement reports.

The reports are produced by ``scripts/rlvr_measure.py`` and committed under
``evaluation/reports/``. This router only reads them — it never runs the
measurement. Running a measurement from an HTTP handler would make the
reported numbers depend on who last hit the endpoint, and the whole point of
the artifact is that it is reproducible from a commit.

Endpoints:
    GET /api/rlvr/report            latest report, full JSON
    GET /api/rlvr/report/           the same data as a static HTML debug view
    GET /api/rlvr/report/summary    just the headline numbers
    GET /api/rlvr/ui                alias for the HTML debug view
    GET /api/rlvr/history           one summary per run, oldest first
    GET /api/rlvr/trajectories      LIVE extraction candidates + per-run rollup

``/trajectories`` is a different artifact from everything above it. The report
routes serve a frozen 16-case golden study that only changes when someone reruns
``rlvr_measure.py``; ``/trajectories`` serves what the extractor actually
produced on real documents, and grows with every run. Rendering them in one view
without saying which is which is the error this docstring exists to prevent.

The ``/report/`` (trailing slash) and ``/ui`` routes serve a self-contained
HTML page that renders the JSON endpoints above — same data, easier to look
at. It is intentionally dependency-free (no CDN, no build step), so it works
offline just like the measurement that feeds it.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/api/rlvr", tags=["rlvr"])

# ai-service/api/rlvr.py -> parents[2] == repo root
REPORTS_DIR = Path(__file__).resolve().parents[2] / "evaluation" / "reports"
REPORT_PATH = REPORTS_DIR / "rlvr-measurement.json"
HISTORY_PATH = REPORTS_DIR / "rlvr-measurement-history.jsonl"

_MISSING = (
    "No RLVR measurement has been generated yet. "
    "Run `python3 scripts/rlvr_measure.py` (offline, no API calls)."
)

# The LIVE artifact — one record per candidate the extractor actually returned,
# written by the orchestrator. Distinct from the measurement report above in
# every way that matters: the report is a frozen 16-case golden study rerun by
# hand, this grows on every extraction. Serving them from one router is
# convenient; conflating them in a view is the mistake to avoid.
TRAJECTORY_PATH = (
    Path(__file__).resolve().parents[2] / "evaluation" / "trajectories" / "trajectory.jsonl"
)

_NO_TRAJECTORIES = (
    "No extraction candidates logged yet. Run an extraction "
    "(`python main.py --economy SGP --pillar 6,7`) with RDTII_TRAJECTORY_LOG unset or on."
)

UI_PATH = Path(__file__).resolve().with_name("rlvr_ui.html")


def _ui_page() -> HTMLResponse:
    """The static debug view, read fresh so live edits survive a browser reload.

    Served even when no report exists yet: the page itself fetches the JSON
    endpoints and renders the missing-report message from their 404 detail,
    which is more useful while debugging than a bare 404 page.
    """
    try:
        content = UI_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"rlvr UI page is missing: {exc}"
        ) from exc
    return HTMLResponse(content)


@router.get("/report/", include_in_schema=False)
def rlvr_report_ui() -> HTMLResponse:
    """Static HTML debug view of the latest measurement."""
    return _ui_page()


@router.get("/report/ui", include_in_schema=False)
def rlvr_report_ui_alias() -> HTMLResponse:
    """Another alias for the static HTML debug view."""
    return _ui_page()


@router.get("/ui", include_in_schema=False)
def rlvr_ui() -> HTMLResponse:
    """Alias for the static HTML debug view."""
    return _ui_page()


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


def _load_trajectories() -> list[dict]:
    """Every logged candidate, oldest first. Tolerates a torn tail.

    The file is appended concurrently by chunk workers under a lock, but a run
    killed mid-write can still leave a partial last line. Skipping it beats
    404-ing a view over thousands of good records.
    """
    if not TRAJECTORY_PATH.exists():
        raise HTTPException(status_code=404, detail=_NO_TRAJECTORIES)
    records = []
    for line in TRAJECTORY_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not records:
        raise HTTPException(status_code=404, detail=_NO_TRAJECTORIES)
    return records


def _rollup(records: list[dict]) -> list[dict]:
    """One row per extraction run, newest first.

    Mean proxy is the headline per run, but `gate_failures` is the number worth
    watching: a gate failure collapses the reward to 0, so it marks a candidate
    the pipeline returned and the label-free reward considers unusable.
    """
    runs: dict[str, dict] = {}
    for record in records:
        run_id = str(record.get("run_id") or "unknown")
        proxy = record.get("proxy") or {}
        entry = runs.setdefault(
            run_id,
            {
                "run_id": run_id,
                "provider": record.get("provider") or "unknown",
                "model": record.get("model") or "unknown",
                "started_at": record.get("logged_at"),
                "last_at": record.get("logged_at"),
                "records": 0,
                "gate_failures": 0,
                "indicators": set(),
                "documents": set(),
                "_proxy_total": 0.0,
                "_proxy_n": 0,
            },
        )
        entry["records"] += 1
        entry["last_at"] = record.get("logged_at") or entry["last_at"]
        entry["indicators"].add(str(record.get("indicator_id") or "?"))
        entry["documents"].add(str(record.get("document_id") or "?"))
        if proxy.get("passed_gates") is False:
            entry["gate_failures"] += 1
        total = proxy.get("total")
        if isinstance(total, (int, float)):
            entry["_proxy_total"] += float(total)
            entry["_proxy_n"] += 1

    out = []
    for entry in runs.values():
        n = entry.pop("_proxy_n")
        total = entry.pop("_proxy_total")
        entry["mean_proxy"] = (total / n) if n else None
        entry["indicators"] = sorted(entry["indicators"])
        entry["documents"] = len(entry["documents"])
        out.append(entry)
    out.sort(key=lambda e: str(e.get("last_at") or ""), reverse=True)
    return out


@router.get("/trajectories")
def rlvr_trajectories(
    limit: int = 200,
    run_id: str | None = None,
    indicator_id: str | None = None,
) -> dict:
    """Live extraction candidates with their proxy reward, newest first.

    This is what the extractor ACTUALLY produced, as opposed to /report, which
    is a frozen golden-set study. Callers should not blend the two: with
    best-of-N unwired every record here is a single greedy draw (k=1), so there
    are no preference pairs and no top-1 rate to compute — only the distribution
    of proxy scores over real output.

    ``selected`` is True on every row for the same reason; it is carried so the
    shape does not change when best-of-N is eventually wired.
    """
    records = _load_trajectories()
    runs = _rollup(records)

    filtered = records
    if run_id:
        filtered = [r for r in filtered if r.get("run_id") == run_id]
    if indicator_id:
        filtered = [r for r in filtered if str(r.get("indicator_id")) == indicator_id]

    newest_first = list(reversed(filtered))
    trimmed = newest_first[:limit] if limit > 0 else newest_first
    return {
        "runs": runs,
        "records": trimmed,
        "total": len(records),
        "matched": len(filtered),
        "returned": len(trimmed),
        "path": str(TRAJECTORY_PATH),
        # Stated in the payload, not just the docs: any client rendering this
        # next to /report needs to know they are different measurements.
        "note": (
            "Live extraction candidates (k=1, greedy). Not the golden-set "
            "measurement — see /api/rlvr/report for that."
        ),
    }
