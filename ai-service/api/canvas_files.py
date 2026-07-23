from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from auth import get_current_user

from services import canvas_file_ingest as ingest

router = APIRouter(prefix="/api/canvas-files")
MAX_UPLOAD_BYTES = 25_000_000  # 25MB


class UploadResponse(BaseModel):
    document_id: str
    status: str
    deduplicated: bool
    chunks: int | None = None  # populated only on a sync ingest


class StatusResponse(BaseModel):
    document_id: str
    status: str


@router.post("", response_model=UploadResponse)
async def upload_canvas_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    country_code: str | None = Form(default=None),
    sync: bool = Query(
        default=False,
        description="Run _save_to_db inline and return the final processed "
        "state (chunk count) instead of processing in the background. Used by "
        "the TUI / scripted ingest so the caller can scope a query immediately.",
    ),
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

    if result["deduplicated"] and result["status"] != "failed":
        # Already ingested (and not a prior failure) — nothing to (re)process.
        return UploadResponse(**result)

    if sync:
        # Fire _save_to_db inline (off the event loop — it embeds + writes DB)
        # and hand back the final state, so the caller need not poll.
        try:
            done = await run_in_threadpool(ingest._save_to_db, result["document_id"])
        except ingest.CanvasIngestError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return UploadResponse(**{**result, **done})

    background_tasks.add_task(ingest._save_to_db, result["document_id"])
    return UploadResponse(**result)


@router.post("/{document_id}/process", response_model=UploadResponse)
async def process_canvas_file(
    document_id: str,
    current_user: dict = Depends(get_current_user),
) -> UploadResponse:
    """(Re)run extract → chunk → embed for an already-registered document.

    Completes a document stuck in 'processing' (its background task never ran)
    and re-embeds it. Fires _save_to_db inline and returns the final state;
    _save_to_db marks the document 'failed' on error.
    """
    if ingest.get_status(document_id) is None:
        raise HTTPException(status_code=404, detail="Unknown document.")
    try:
        done = await run_in_threadpool(ingest._save_to_db, document_id)
    except ingest.CanvasIngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return UploadResponse(
        document_id=document_id,
        status=done.get("status", "processed"),
        deduplicated=False,
        chunks=done.get("chunks"),
    )


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


@router.get("", response_model=list[dict])
async def list_canvas_files(
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """List ingested documents (newest first) for the Documents panel."""
    return ingest.list_documents()


@router.post("/audit-countries")
async def audit_countries(
    fix: bool = False,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Audit (and optionally repair) stored country codes against detection."""
    return ingest.audit_country_codes(fix=fix)
