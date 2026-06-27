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
        return create_excel_response(
            mappings=req.mappings,
            country=req.country,
            filename=req.filename,
        )
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"Excel export unavailable: {exc}. Install openpyxl.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Excel export failed: {str(exc)}")

