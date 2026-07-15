from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from schemas import IndicatorMapping

router = APIRouter()


class ExcelExportRequest(BaseModel):
    country: str = "unknown"
    mappings: list[IndicatorMapping] = []
    filename: str = "rdtii_mappings.xlsx"
    # Opt-in "clean export": drop weak-evidence rows (mid-sentence fragments and
    # bare title-quotes on non-framework indicators) using the same rule as the
    # submission noise-gate. Default False so the frontend keeps exporting
    # exactly what it shows unless it asks for a filtered export.
    drop_weak: bool = False


@router.post("/api/excel/export")
async def export_excel(req: ExcelExportRequest):
    from excel_exporter import create_excel_response

    mappings = req.mappings
    dropped = 0
    if req.drop_weak:
        mappings, dropped = _drop_weak_mappings(req.mappings)

    try:
        response = create_excel_response(
            mappings=mappings,
            country=req.country,
            filename=req.filename,
        )
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Excel export unavailable: {exc}. Install openpyxl.",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Excel export failed: {str(exc)}")

    _log_export(req, exported=len(mappings), dropped=dropped)
    return response


def _drop_weak_mappings(mappings: list[IndicatorMapping]) -> tuple[list[IndicatorMapping], int]:
    """Filter out weak-evidence rows, reusing the submission noise-gate rule.

    Best-effort: if the submission module can't be imported, nothing is dropped
    (a filter failure must never silently blank an export)."""
    try:
        from submission.schema import _is_weak_evidence, indicator_to_rdtii_code
    except Exception:  # noqa: BLE001
        return mappings, 0

    kept: list[IndicatorMapping] = []
    for m in mappings:
        try:
            code = indicator_to_rdtii_code(str(getattr(m, "indicator", "")))
        except Exception:  # noqa: BLE001
            code = ""
        if _is_weak_evidence(
            str(getattr(m, "source_legislation", "") or ""),
            str(getattr(m, "verbatim_quote", "") or ""),
            code,
        ):
            continue
        kept.append(m)
    return kept, len(mappings) - len(kept)


def _log_export(req: ExcelExportRequest, *, exported: int, dropped: int) -> None:
    try:
        from services.activity_log import record_activity

        summary = f"Exported {exported} mapping(s) to {req.filename}"
        if dropped:
            summary += f" ({dropped} weak row(s) dropped)"
        record_activity(
            "export", target_type="economy", target_id=req.country, economy=req.country,
            summary=summary,
            detail={"rows": exported, "dropped_weak": dropped, "filename": req.filename},
        )
    except Exception:  # noqa: BLE001 — logging must never break the export
        pass
