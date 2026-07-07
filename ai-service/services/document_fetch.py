from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field


class CrawlQuality(BaseModel):
    status: str = "unknown"
    should_extract: bool = False
    char_count: int = 0
    word_count: int = 0
    legal_signal_score: int = 0
    warnings: list[str] = Field(default_factory=list)


class DocumentText(BaseModel):
    source_url: str
    text: str
    content_type: str = "text"
    pdf_metadata: dict[str, Any] | None = None
    crawl_metadata: dict[str, Any] = Field(default_factory=dict)
    quality: CrawlQuality = Field(default_factory=CrawlQuality)


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
        text = crawl_result.get("text", "")
        quality = assess_crawl_quality(text, source_url=source_url, content_type="text")
        return DocumentText(
            source_url=source_url,
            text=text,
            content_type="text",
            crawl_metadata=_crawl_metadata(crawl_result, source_url, browser_mode),
            quality=quality,
        )
    if result_type == "docx":
        text = crawl_result.get("text", "")
        quality = assess_crawl_quality(text, source_url=source_url, content_type="docx")
        return DocumentText(
            source_url=source_url,
            text=text,
            content_type="docx",
            crawl_metadata=_crawl_metadata(crawl_result, source_url, browser_mode),
            quality=quality,
        )
    if result_type == "pdf":
        pdf_path = crawl_result.get("pdf_path")
        if not pdf_path:
            raise ValueError("Crawler returned a PDF result without pdf_path.")
        pdf_result = await asyncio.to_thread(read_pdf, pdf_path, source_url=source_url)
        text = "\n".join(pdf_result.pages)
        quality = assess_crawl_quality(text, source_url=source_url, content_type="pdf")
        return DocumentText(
            source_url=source_url,
            text=text,
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
            crawl_metadata=_crawl_metadata(crawl_result, source_url, browser_mode),
            quality=quality,
        )

    message = crawl_result.get("message", "unknown error")
    raise ValueError(f"Crawl failed: {message}")


LEGAL_SIGNAL_TERMS = (
    "act",
    "regulation",
    "regulations",
    "law",
    "section",
    "article",
    "clause",
    "personal data",
    "data protection",
    "cybersecurity",
    "cross-border",
    "transfer",
    "commission",
    "authority",
    "shall",
    "must",
    "pdpa",
    "个人信息",
    "网络安全",
    "数据出境",
    "มาตรา",
    "พระราชบัญญัติ",
)

ERROR_PAGE_TERMS = (
    "page not found",
    "404",
    "not found",
    "access denied",
    "forbidden",
    "enable javascript",
    "captcha",
    "just a moment",
    "cloudflare",
    "request could not be satisfied",
    "temporarily unavailable",
)

NAVIGATION_TERMS = (
    "home",
    "about",
    "contact",
    "search",
    "menu",
    "privacy policy",
    "terms of use",
    "subscribe",
    "share",
)


def assess_crawl_quality(text: str, *, source_url: str = "", content_type: str = "text") -> CrawlQuality:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    lower = normalized.casefold()
    char_count = len(normalized)
    words = re.findall(r"[\w\u4e00-\u9fff\u0e00-\u0e7f]+", lower)
    word_count = len(words)
    legal_signal_score = sum(1 for term in LEGAL_SIGNAL_TERMS if term.casefold() in lower)
    warnings: list[str] = []

    if not normalized:
        return CrawlQuality(
            status="empty",
            should_extract=False,
            char_count=0,
            word_count=0,
            legal_signal_score=0,
            warnings=["Crawler returned no text."],
        )

    if any(term in lower for term in ERROR_PAGE_TERMS) and char_count < 5000:
        warnings.append("Fetched text looks like an error, block, or challenge page.")
        return CrawlQuality(
            status="error_page",
            should_extract=False,
            char_count=char_count,
            word_count=word_count,
            legal_signal_score=legal_signal_score,
            warnings=warnings,
        )

    if char_count < 800:
        warnings.append("Fetched text is short; it may be a landing page or incomplete crawl.")

    if legal_signal_score < 2:
        warnings.append("Fetched text has few legal-domain signals.")

    if _looks_navigation_heavy(lower, word_count):
        warnings.append("Fetched text appears navigation-heavy.")

    if _domain_mismatch(source_url, lower):
        warnings.append("Fetched text may not match the requested official source domain.")

    status = "good"
    if warnings:
        status = "weak"
    if char_count >= 1600 and legal_signal_score >= 2 and not _looks_navigation_heavy(lower, word_count):
        status = "good"
        warnings = [warning for warning in warnings if "short" not in warning and "few legal" not in warning]

    return CrawlQuality(
        status=status,
        should_extract=status == "good",
        char_count=char_count,
        word_count=word_count,
        legal_signal_score=legal_signal_score,
        warnings=warnings,
    )


def _crawl_metadata(crawl_result: dict[str, Any], source_url: str, browser_mode: str) -> dict[str, Any]:
    metadata = crawl_result.get("metadata")
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    final_url = str(crawl_result.get("url") or source_url)
    fetch_method = str(metadata.get("source") or _default_fetch_method(crawl_result.get("type")))
    return {
        "requested_url": source_url,
        "final_url": final_url,
        "fetch_method": fetch_method,
        "browser_mode": browser_mode,
        "title": metadata.get("title") or "",
        "selector": metadata.get("selector") or "",
        "source_metadata": metadata,
    }


def _default_fetch_method(result_type: Any) -> str:
    if result_type == "pdf":
        return "download"
    if result_type == "docx":
        return "download"
    return "crawler"


def _looks_navigation_heavy(lower: str, word_count: int) -> bool:
    if word_count < 25:
        return False
    nav_hits = sum(lower.count(term) for term in NAVIGATION_TERMS)
    return nav_hits >= 8 and nav_hits / max(word_count, 1) > 0.08


def _domain_mismatch(source_url: str, lower: str) -> bool:
    domain = urlparse(source_url).netloc.lower().removeprefix("www.")
    if not domain or "." not in domain:
        return False
    domain_stem = domain.split(".", 1)[0]
    return len(domain_stem) >= 4 and domain_stem not in lower and len(lower) < 1200
