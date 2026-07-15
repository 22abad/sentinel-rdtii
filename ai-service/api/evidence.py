"""Verified-evidence API — bank extraction results and reuse approved ones.

Backs the "materials go into a library, avoid repeat work" story at the results
layer: POST to bank a run's mappings (deduped), GET to reuse them, and review to
promote a draft to approved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter()


class EvidenceItem(BaseModel):
    indicator_id: str
    law_name: str
    verbatim_quote: str
    article: str | None = None
    source_url: str | None = None
    source_sha256: str | None = None
    score: float | None = None


class SaveEvidenceRequest(BaseModel):
    economy: str
    items: list[EvidenceItem] = Field(default_factory=list)
    review_status: str = "draft"


class ReviewRequest(BaseModel):
    status: str  # approved | rejected | draft


@router.post("/api/evidence")
async def bank_evidence(req: SaveEvidenceRequest) -> dict[str, Any]:
    """Bank a run's verified mappings; already-known ones are deduplicated."""
    from services.evidence_store import save_evidence

    result = save_evidence(
        req.economy, [it.model_dump() for it in req.items],
        review_status=req.review_status,
    )
    return result


@router.get("/api/evidence")
async def get_evidence(
    economy: str = Query(...),
    indicator_id: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    """Return banked evidence for an economy — the reuse source."""
    from services.evidence_store import find_evidence

    items = find_evidence(
        economy, indicator_id=indicator_id, review_status=review_status, limit=limit,
    )
    return {"items": items, "count": len(items)}


@router.post("/api/evidence/{evidence_id}/review")
async def review_evidence(evidence_id: str, req: ReviewRequest) -> dict[str, Any]:
    """Promote/reject a banked row (draft -> approved/rejected)."""
    from fastapi import HTTPException

    from services.evidence_store import set_review_status

    if not set_review_status(evidence_id, req.status):
        raise HTTPException(status_code=400, detail="invalid status or evidence id not found")
    return {"id": evidence_id, "review_status": req.status}
