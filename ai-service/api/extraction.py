from __future__ import annotations

import asyncio
import json
import os
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from providers import get_provider
from providers.base import ExtractionError
from schemas import ExtractionResponse
from services.extraction import run_extraction
from services.streaming_extraction import stream_extraction

router = APIRouter()


def _is_thai_query(text: str) -> bool:
    thai_chars = sum(1 for char in text if "\u0E00" <= char <= "\u0E7F")
    return thai_chars > 0 and len(text) < 200


def _is_garbage_content(text: str) -> bool:
    if len(text) < 500:
        return True
    garbage_signals = [
        "window.addEventListener",
        "DOMContentLoaded",
        "archive_analytics",
        "performing security",
        "just a moment",
        "cloudflare ray id",
        "webpackJsonp",
        "this.addEventListener",
    ]
    return any(signal in text.lower()[:2000] for signal in garbage_signals)


def _is_error_page_content(text: str) -> bool:
    if not text or not text.strip():
        return True
    lowered = " ".join(text.lower().split())
    error_signals = [
        "page not found",
        "404 not found",
        "404 error",
        "the page you are looking for may have been removed",
        "had its name changed",
        "temporarily unavailable",
        "website address displayed in the address bar",
        "this page could not be found",
        "the requested url was not found",
    ]
    return any(signal in lowered[:3000] for signal in error_signals)


async def _fetch_with_browser_mode(fetcher, source_url: str, browser_mode: str):
    import inspect

    sig = inspect.signature(fetcher)
    accepts_mode = "browser_mode" in sig.parameters or any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for param in sig.parameters.values()
    )
    if accepts_mode:
        return await fetcher(source_url, browser_mode=browser_mode)
    return await fetcher(source_url)


def _read_pdf_with_optional_source(read_pdf_func, pdf_path: str, source_url: str = ""):
    import inspect

    sig = inspect.signature(read_pdf_func)
    accepts_source_url = "source_url" in sig.parameters or any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for param in sig.parameters.values()
    )
    if accepts_source_url:
        return read_pdf_func(pdf_path, source_url=source_url)
    return read_pdf_func(pdf_path)


def _configured_provider(provider: str | None, model: str | None):
    if provider:
        return get_provider(provider, model=model)

    import main as main_module

    return main_module._get_provider()


@router.post("/api/extract", response_model=ExtractionResponse)
async def extract(
    text: str = Form(""),
    source_url: str = Form(""),
    provider: str = Form(None),
    model: str = Form(None),
    browser_mode: str = Form("auto"),
):
    from crawler import fetch_legal_content, fetch_thai_law_by_keyword
    from pdf_reader import read_pdf

    original_text = text
    pdf_meta = None

    if source_url.strip():
        crawl_result = await _fetch_with_browser_mode(fetch_legal_content, source_url, browser_mode)

        if crawl_result["type"] == "text":
            text = crawl_result["text"]
            if _is_error_page_content(text):
                raise HTTPException(status_code=400, detail="Crawl returned a website error page; choose another candidate URL.")
            if _is_garbage_content(text) and _is_thai_query(original_text):
                print(f"[extract] crawled content looked unusable; trying OCS search: {original_text[:60]}")
                ocs_result = await fetch_thai_law_by_keyword(original_text.strip())
                if ocs_result["type"] == "text":
                    text = ocs_result["text"]
        elif crawl_result["type"] == "pdf":
            try:
                pdf_result = await asyncio.to_thread(_read_pdf_with_optional_source, read_pdf, crawl_result["pdf_path"], source_url)
                text = "\n".join(pdf_result.pages)
                pdf_meta = {
                    "_ocr_mean_confidence": round(pdf_result.mean_conf, 3),
                    "_ocr_ratio": round(pdf_result.ocr_ratio, 3),
                    "_pdf_type": "scanned" if pdf_result.ocr_ratio > 0.5 else "mixed" if pdf_result.ocr_ratio > 0 else "pure_text",
                }
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"PDF parsing failed: {str(exc)}")
        elif crawl_result["type"] == "docx":
            text = crawl_result["text"]
        else:
            if _is_thai_query(original_text):
                print(f"[extract] URL crawl failed; trying OCS search: {original_text[:60]}")
                ocs_result = await fetch_thai_law_by_keyword(original_text.strip())
                if ocs_result["type"] == "text":
                    text = ocs_result["text"]
                else:
                    raise HTTPException(status_code=400, detail=f"Crawl failed: {crawl_result['message']}")
            else:
                raise HTTPException(status_code=400, detail=f"Crawl failed: {crawl_result['message']}")
    elif _is_thai_query(text):
        print(f"[extract] Thai search term detected; trying OCS search: {text[:60]}")
        ocs_result = await fetch_thai_law_by_keyword(text.strip())
        if ocs_result["type"] == "text":
            text = ocs_result["text"]
        else:
            print(f"[extract] OCS search returned no result: {ocs_result.get('message', '')}")

    if not text.strip():
        raise HTTPException(status_code=400, detail="No text provided and crawl returned no content.")

    try:
        llm_provider = _configured_provider(provider, model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ExtractionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return await run_extraction(text, llm_provider, pdf_metadata=pdf_meta)


@router.post("/api/extract/stream")
async def extract_stream(
    text: str = Form(""),
    source_url: str = Form(""),
    provider: str = Form(None),
    model: str = Form(None),
    browser_mode: str = Form("auto"),
):
    from crawler import fetch_legal_content, fetch_thai_law_by_keyword
    from pdf_reader import read_pdf

    def _sse(event, payload):
        return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"

    original_text = text
    pdf_meta = None

    if source_url.strip():
        crawl_result = await _fetch_with_browser_mode(fetch_legal_content, source_url, browser_mode)
        if crawl_result["type"] == "text":
            text = crawl_result["text"]
            if _is_error_page_content(text):
                async def _error_page():
                    yield _sse("error", {"detail": "Crawl returned a website error page; choose another candidate URL."})

                return StreamingResponse(_error_page(), media_type="text/event-stream")
            if _is_garbage_content(text) and _is_thai_query(original_text):
                ocs_result = await fetch_thai_law_by_keyword(original_text.strip())
                if ocs_result["type"] == "text":
                    text = ocs_result["text"]
        elif crawl_result["type"] == "pdf":
            try:
                pdf_result = await asyncio.to_thread(_read_pdf_with_optional_source, read_pdf, crawl_result["pdf_path"], source_url)
                text = "\n".join(pdf_result.pages)
                pdf_meta = {
                    "_ocr_mean_confidence": round(pdf_result.mean_conf, 3),
                    "_ocr_ratio": round(pdf_result.ocr_ratio, 3),
                    "_pdf_type": "scanned" if pdf_result.ocr_ratio > 0.5 else "mixed" if pdf_result.ocr_ratio > 0 else "pure_text",
                }
            except Exception as exc:
                detail = f"PDF parsing failed: {str(exc)}"

                async def _error():
                    yield _sse("error", {"detail": detail})

                return StreamingResponse(_error(), media_type="text/event-stream")
        elif crawl_result["type"] == "docx":
            text = crawl_result["text"]
        else:
            if _is_thai_query(original_text):
                ocs_result = await fetch_thai_law_by_keyword(original_text.strip())
                if ocs_result["type"] == "text":
                    text = ocs_result["text"]
                else:
                    async def _err():
                        yield _sse("error", {"detail": f"Crawl failed: {crawl_result['message']}"})

                    return StreamingResponse(_err(), media_type="text/event-stream")
            else:
                async def _err():
                    yield _sse("error", {"detail": f"Crawl failed: {crawl_result['message']}"})

                return StreamingResponse(_err(), media_type="text/event-stream")
    elif _is_thai_query(text):
        ocs_result = await fetch_thai_law_by_keyword(text.strip())
        if ocs_result["type"] == "text":
            text = ocs_result["text"]

    if not text.strip():
        async def _empty():
            yield _sse("error", {"detail": "No text provided and crawl returned no content."})

        return StreamingResponse(_empty(), media_type="text/event-stream")

    try:
        llm_provider = _configured_provider(provider, model)
    except (ValueError, ExtractionError) as exc:
        detail = str(exc)

        async def _bad_provider():
            yield _sse("error", {"detail": detail})

        return StreamingResponse(_bad_provider(), media_type="text/event-stream")

    return StreamingResponse(
        stream_extraction(text, llm_provider, pdf_metadata=pdf_meta),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/upload", response_model=ExtractionResponse)
async def upload(file: UploadFile = File(...), provider: str = Form(None), model: str = Form(None)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    from pdf_reader import read_pdf

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    try:
        content = await file.read()
        await asyncio.to_thread(tmp.write, content)
        tmp.close()

        pdf_result = await asyncio.to_thread(_read_pdf_with_optional_source, read_pdf, tmp.name)
        text = "\n".join(pdf_result.pages)
        pdf_meta = {
            "_ocr_mean_confidence": round(pdf_result.mean_conf, 3),
            "_ocr_ratio": round(pdf_result.ocr_ratio, 3),
            "_pdf_type": "scanned" if pdf_result.ocr_ratio > 0.5 else "mixed" if pdf_result.ocr_ratio > 0 else "pure_text",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF parsing failed: {str(exc)}")
    finally:
        await asyncio.to_thread(os.unlink, tmp.name)

    if not text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from the PDF.")

    try:
        llm_provider = _configured_provider(provider, model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ExtractionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return await run_extraction(text, llm_provider, pdf_metadata=pdf_meta)


@router.post("/api/ingest/document", response_model=ExtractionResponse)
async def ingest_document(file: UploadFile = File(...), provider: str = Form(None), model: str = Form(None)):
    return await upload(file, provider, model)


@router.post("/api/parse-file")
async def parse_file(file: UploadFile = File(...)):
    """Extract text from an uploaded PDF WITHOUT running the LLM pipeline.

    Used by the workbench canvas: linking a file node to the Source panel
    registers it as a source; Run parses it here and feeds the text through
    the normal streaming extraction (so progress display keeps working).
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    from pdf_reader import read_pdf

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    try:
        content = await file.read()
        await asyncio.to_thread(tmp.write, content)
        tmp.close()
        pdf_result = await asyncio.to_thread(_read_pdf_with_optional_source, read_pdf, tmp.name)
        text = "\n".join(pdf_result.pages)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF parsing failed: {str(exc)}")
    finally:
        await asyncio.to_thread(os.unlink, tmp.name)

    if not text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from the PDF.")

    return {
        "text": text,
        "pdf_metadata": {
            "_ocr_mean_confidence": round(pdf_result.mean_conf, 3),
            "_ocr_ratio": round(pdf_result.ocr_ratio, 3),
            "_pdf_type": "scanned" if pdf_result.ocr_ratio > 0.5 else "mixed" if pdf_result.ocr_ratio > 0 else "pure_text",
        },
    }


class FetchTextRequest(BaseModel):
    source_url: str = ""
    browser_mode: str = "auto"


class FetchTextResponse(BaseModel):
    text: str = ""
    pdf_metadata: dict | None = None


@router.post("/api/fetch-text")
async def fetch_text(req: FetchTextRequest):
    from crawler import fetch_legal_content
    from pdf_reader import read_pdf

    if not req.source_url.strip():
        raise HTTPException(status_code=400, detail="source_url is required.")

    crawl_result = await fetch_legal_content(req.source_url, browser_mode=req.browser_mode)
    if crawl_result["type"] == "text":
        return FetchTextResponse(text=crawl_result["text"])
    if crawl_result["type"] == "pdf":
        try:
            pdf_result = await asyncio.to_thread(_read_pdf_with_optional_source, read_pdf, crawl_result["pdf_path"], req.source_url)
            return {
                "text": "\n".join(pdf_result.pages),
                "pdf_metadata": {
                    "mean_confidence": round(pdf_result.mean_conf, 3),
                    "ocr_ratio": round(pdf_result.ocr_ratio, 3),
                    "pdf_type": "scanned" if pdf_result.ocr_ratio > 0.5 else "mixed" if pdf_result.ocr_ratio > 0 else "pure_text",
                    "total_pages": pdf_result.total_pages,
                    "ocr_pages": pdf_result.ocr_pages,
                    "text_pages": pdf_result.text_pages,
                },
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PDF parsing failed: {str(exc)}")
    if crawl_result["type"] == "docx":
        return FetchTextResponse(text=crawl_result["text"])
    raise HTTPException(status_code=400, detail=f"Crawl failed: {crawl_result.get('message', 'unknown error')}")


class LegalSearchRequest(BaseModel):
    query: str
    country_code: str = "CHN"
    limit: int = 10
    browser_mode: str = "opencli"


@router.post("/api/legal-search")
async def legal_search(req: LegalSearchRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required.")
    if req.country_code.upper() != "CHN":
        raise HTTPException(status_code=400, detail="Only CHN legal search is implemented in this MVP.")

    from browser_drivers import BrowserFetchError, OpenCliBrowserDriver

    try:
        results = await OpenCliBrowserDriver().search_gov_law(
            req.query,
            limit=max(1, min(req.limit, 20)),
        )
    except BrowserFetchError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {
        "country_code": "CHN",
        "source": "flk.npc.gov.cn",
        "results": results,
    }
