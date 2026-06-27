from __future__ import annotations

from fastapi import APIRouter, HTTPException

from discovery import DiscoverySearchRequest, DiscoveryService
from discovery.registry import get_sources

router = APIRouter()
_discovery_service = DiscoveryService()


@router.post("/api/discovery/search")
async def discovery_search(req: DiscoverySearchRequest):
    try:
        return await _discovery_service.search(req)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No discovery sources configured for {req.country_code}.")


@router.get("/api/discovery/sources/{country_code}")
async def discovery_sources(country_code: str):
    normalized = country_code.strip().upper()
    try:
        sources = get_sources(normalized)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No discovery sources configured for {normalized}.")
    return {
        "country_code": normalized,
        "sources": [source.model_dump() for source in sources],
    }

