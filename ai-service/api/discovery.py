from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from discovery import DiscoverySearchRequest, DiscoveryService
from discovery.registry import (
    clear_registry_cache,
    get_registry,
    get_registry_backend,
    get_sources,
    list_countries,
    save_file_registry,
)
from services import discovery_source_persistence

router = APIRouter()
_discovery_service = DiscoveryService()


class DiscoveryRegistryUpdateRequest(BaseModel):
    registry: dict[str, Any]


@router.post("/api/discovery/search")
async def discovery_search(req: DiscoverySearchRequest):
    try:
        return await _discovery_service.search(req)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No discovery sources configured for {req.country_code}.")
    except discovery_source_persistence.DiscoverySourcePersistenceError as exc:
        raise HTTPException(status_code=503, detail=f"Discovery source database unavailable: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=f"Discovery source configuration invalid: {exc}") from exc


@router.get("/api/discovery/sources/{country_code}")
async def discovery_sources(country_code: str):
    normalized = country_code.strip().upper()
    try:
        sources = get_sources(normalized)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No discovery sources configured for {normalized}.")
    except discovery_source_persistence.DiscoverySourcePersistenceError as exc:
        raise HTTPException(status_code=503, detail=f"Discovery source database unavailable: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=f"Discovery source configuration invalid: {exc}") from exc
    return {
        "country_code": normalized,
        "sources": [source.model_dump() for source in sources],
    }


@router.get("/api/discovery/countries")
async def discovery_countries():
    try:
        return {
            "countries": [country.model_dump() for country in list_countries()],
        }
    except discovery_source_persistence.DiscoverySourcePersistenceError as exc:
        raise HTTPException(status_code=503, detail=f"Discovery source database unavailable: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=f"Discovery source configuration invalid: {exc}") from exc


@router.get("/api/discovery/config")
async def discovery_config():
    try:
        return {"registry": get_registry()}
    except discovery_source_persistence.DiscoverySourcePersistenceError as exc:
        raise HTTPException(status_code=503, detail=f"Discovery source database unavailable: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=f"Discovery source configuration invalid: {exc}") from exc


@router.put("/api/discovery/config")
async def update_discovery_config(
    req: DiscoveryRegistryUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        backend = get_registry_backend()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=f"Discovery source configuration invalid: {exc}") from exc

    try:
        if backend == "file":
            registry = save_file_registry(req.registry)
        else:
            registry = discovery_source_persistence.save_registry(
                req.registry,
                changed_by=current_user.get("user_id"),
                change_note="Saved from Discovery Source Manager",
            )
            clear_registry_cache()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except discovery_source_persistence.DiscoverySourcePersistenceError as exc:
        raise HTTPException(status_code=503, detail=f"Discovery source database unavailable: {exc}") from exc
    return {"registry": registry}
