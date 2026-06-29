from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field


class DocumentText(BaseModel):
    source_url: str
    text: str
    content_type: str = "text"
    pdf_metadata: dict[str, Any] | None = None


async def fetch_document_text(source_url: str, browser_mode: str = "auto") -> DocumentText:
    """Fetch a URL/PDF/DOCX source into normalized document text."""
    from crawler import fetch_legal_content
    from pdf_reader import read_pdf

    source_url = source_url.strip()
    if not source_url:
        raise ValueError("source_url is required.")

    crawl_result = await fetch_legal_content(source_url, browser_mode=browser_mode)
    result_type = crawl_result.get("type")
    if result_type == "text":
        return DocumentText(
            source_url=source_url,
            text=crawl_result.get("text", ""),
            content_type="text",
        )
    if result_type == "docx":
        return DocumentText(
            source_url=source_url,
            text=crawl_result.get("text", ""),
            content_type="docx",
        )
    if result_type == "pdf":
        pdf_path = crawl_result.get("pdf_path")
        if not pdf_path:
            raise ValueError("Crawler returned a PDF result without pdf_path.")
        pdf_result = await asyncio.to_thread(read_pdf, pdf_path)
        return DocumentText(
            source_url=source_url,
            text="\n".join(pdf_result.pages),
            content_type="pdf",
            pdf_metadata={
                "mean_confidence": round(pdf_result.mean_conf, 3),
                "ocr_ratio": round(pdf_result.ocr_ratio, 3),
                "pdf_type": "scanned"
                if pdf_result.ocr_ratio > 0.5
                else "mixed"
                if pdf_result.ocr_ratio > 0
                else "pure_text",
                "total_pages": pdf_result.total_pages,
                "ocr_pages": pdf_result.ocr_pages,
                "text_pages": pdf_result.text_pages,
            },
        )

    message = crawl_result.get("message", "unknown error")
    raise ValueError(f"Crawl failed: {message}")
