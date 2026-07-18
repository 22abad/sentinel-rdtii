from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from country_detector import detect_country

router = APIRouter()


class SourceValidationRequest(BaseModel):
    url: str = ""
    title: str = ""
    text_snippet: str = ""


class SourceValidationResponse(BaseModel):
    grade: str
    confidence: float
    reasons: list[str]
    is_primary: bool
    warning: str = ""


@router.post("/api/validate/source")
def validate_source(req: SourceValidationRequest):
    from source_validator import require_primary_source

    result = require_primary_source(
        url=req.url,
        title=req.title,
        text_snippet=req.text_snippet,
    )
    return SourceValidationResponse(
        grade=result["grade"],
        confidence=result["confidence"],
        reasons=result["reasons"],
        is_primary=result["is_primary"],
        warning=result.get("warning", ""),
    )


class TimestampVerificationRequest(BaseModel):
    url: str = ""
    last_update: str = ""


class TimestampVerificationResponse(BaseModel):
    verified: bool
    best_date: str
    verification_log: str
    source_details: list = []


@router.post("/api/verify/timestamp")
async def verify_timestamp(req: TimestampVerificationRequest):
    try:
        from crawler import verify_law_timeline

        result = await verify_law_timeline(req.url, req.last_update)
        return TimestampVerificationResponse(
            verified=result.get("verified", False),
            best_date=result.get("best_date", ""),
            verification_log=result.get("verification_log", ""),
            source_details=result.get("source_details", []),
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="crawler module not available")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Timestamp verification failed: {str(exc)}")


class ReleaseYearRequest(BaseModel):
    source_legislation: str = ""
    quote: str = ""
    last_update: str = ""
    timeframe_column: str = ""


class ReleaseYearResponse(BaseModel):
    year: int | None = None
    confidence: float = 0.0
    decided_by: str = ""
    candidates: dict = {}
    tally: dict = {}


@router.post("/api/verify/release-year")
async def verify_release_year(req: ReleaseYearRequest):
    """Resolve a law's release year from 4 weighted signals; the LLM decides.

    Needs no source URL — the enactment year usually sits in the citation.
    """
    import asyncio

    from release_year import resolve_release_year

    provider = None
    try:  # the LLM levels are optional — degrade to title/manifest/timeframe
        import main as main_module

        provider = main_module._get_provider()
    except Exception:  # noqa: BLE001
        provider = None
    try:
        result = await asyncio.to_thread(
            resolve_release_year,
            source_legislation=req.source_legislation,
            quote=req.quote,
            last_update=req.last_update,
            timeframe_column=req.timeframe_column,
            provider=provider,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Release-year resolution failed: {str(exc)}")
    return ReleaseYearResponse(**result)


class CoverageRequest(BaseModel):
    provision_text: str = ""
    source_legislation: str = ""
    indicator_id: str = ""


@router.post("/api/classify/coverage")
def classify_coverage_api(req: CoverageRequest):
    from coverage_classifier import classify_coverage

    return classify_coverage(
        provision_text=req.provision_text,
        source_legislation=req.source_legislation,
        indicator_id=req.indicator_id,
    )


class CountryDetectRequest(BaseModel):
    text: str = ""
    source_url: str = ""
    source_legislation: str = ""


@router.post("/api/detect/country")
def detect_country_api(req: CountryDetectRequest):
    return detect_country(
        text=req.text,
        source_url=req.source_url,
        source_legislation=req.source_legislation,
    )

