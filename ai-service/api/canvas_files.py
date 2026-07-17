from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel
from auth import get_current_user

from services import canvas_file_ingest as ingest

router = APIRouter(prefix="/api/canvas-files")
MAX_UPLOAD_BYTES = 25_000_000  # 25MB


class UploadResponse(BaseModel):
    document_id: str
    status: str
    deduplicated: bool


class StatusResponse(BaseModel):
    document_id: str
    status: str


@router.post("", response_model=UploadResponse)
async def upload_canvas_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    country_code: str | None = Form(default=None),
    current_user: dict = Depends(get_current_user),
) -> UploadResponse:
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large (max 25 MB).")
    try:
        result = ingest.register_upload(
            file.filename or "upload",
            data,
            uploaded_by=current_user["user_id"],
            country_code=country_code,
        )
    except ingest.CanvasIngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not result["deduplicated"] or result["status"] == "failed":
        background_tasks.add_task(ingest._save_to_db, result["document_id"])

    return UploadResponse(**result)


@router.get("/{document_id}", response_model=StatusResponse)
async def canvas_file_status(
    document_id: str,
    current_user: dict = Depends(get_current_user),
) -> StatusResponse:
    """Poll ingestion state — processing happens in a background task."""
    status = ingest.get_status(document_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Unknown document.")
    return StatusResponse(document_id=document_id, status=status)


@router.delete("/{document_id}", response_model=StatusResponse)
async def delete_canvas_file(
    document_id: str,
    current_user: dict = Depends(get_current_user),
) -> StatusResponse:
    """Delete an ingested document (and its chunks/embeddings) from the KB."""
    if not ingest.delete_document(document_id):
        raise HTTPException(status_code=404, detail="Unknown document.")
    return StatusResponse(document_id=document_id, status="deleted")
