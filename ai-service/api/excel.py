from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from schemas import IndicatorMapping

router = APIRouter()


class ExcelExportRequest(BaseModel):
    country: str = "unknown"
    mappings: list[IndicatorMapping] = []
    filename: str = "rdtii_mappings.xlsx"


@router.post("/api/excel/export")
async def export_excel(req: ExcelExportRequest):
    from excel_exporter import create_excel_response

    try:
        response = create_excel_response(
            mappings=req.mappings,
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

    _log_export(req)
    return response


def _log_export(req: ExcelExportRequest) -> None:
    try:
        from services.activity_log import record_activity

        record_activity(
            "export", target_type="economy", target_id=req.country, economy=req.country,
            summary=f"Exported {len(req.mappings)} mapping(s) to {req.filename}",
            detail={"rows": len(req.mappings), "filename": req.filename},
        )
    except Exception:  # noqa: BLE001 — logging must never break the export
        pass
