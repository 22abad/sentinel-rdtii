"""
Unified PDF reader — routes to the correct extraction path per page.

Pure text page  → PyMuPDF  (fast, no OCR)
Image/scan page → Tesseract (render → OCR)

Mixed PDFs (e.g. text title page + scanned body) are handled by checking
every page individually rather than routing the whole document at once.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import fitz

from .non_ocr.pymupdf_extractor import (
    _extract_page_filtered,
    _strip_repeated_lines,
    extract_sections_pure,
    is_pure_text_pdf,
    is_garbled,
    text_confidence,
)
from .ocr_service.tesseract_extractor import (
    _DPI,
    _OCR_WORKERS,
    _TESSERACT_LANGS,
    _render_page,
    _timed_ocr_page,
    extract_sections_ocr,
)

logger = logging.getLogger(__name__)

# Minimum characters from PyMuPDF before a page is considered "has text".
# Below this threshold the page is treated as image-only and sent to OCR.
_PAGE_TEXT_MIN = int(os.getenv("PDF_PAGE_TEXT_MIN", "80"))


@dataclass
class PdfResult:
    """Result of a PDF extraction with per-page confidence metadata.

    Attributes:
        pages: Extracted text for each page.
        ocr_ratio:  0.0–1.0 — fraction of pages that needed OCR.
        mean_conf:  0.0–1.0 — average confidence across ALL pages.
        total_pages:  Total number of pages in the PDF.
        ocr_pages:   Number of pages processed via OCR.
        text_pages:  Number of pages extracted via direct text layer.
        page_confs:  Per-page confidence scores (0.0–1.0).
    """
    pages: list[str]
    ocr_ratio: float
    mean_conf: float
    total_pages: int
    ocr_pages: int
    text_pages: int
    page_confs: list[float]


def read_pdf(filepath: str, langs: str = _TESSERACT_LANGS, source_url: str = "") -> PdfResult:
    """Extract text from a PDF with per-page routing and confidence tracking.

    Each page is checked individually:
    - If PyMuPDF yields >= PDF_PAGE_TEXT_MIN chars after watermark filtering → use it.
    - Otherwise → OCR that page with Tesseract.

    Returns a PdfResult with per-page confidence scores.
    """
    sidecar_result = _read_pdf_via_sidecar(filepath, source_url=source_url)
    if sidecar_result is not None:
        return sidecar_result

    import time
    from concurrent.futures import ThreadPoolExecutor, Future

    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {filepath}")

    t0 = time.perf_counter()
    doc = fitz.open(str(path))
    n_pages = len(doc)
    logger.info("[PDF] read_pdf  pages=%d  file=%s", n_pages, path.name)

    # First pass: extract text layer + detect image blocks for every page.
    pymupdf_pages: list[str] = []
    has_images: list[bool] = []
    for page in doc:
        pymupdf_pages.append(_extract_page_filtered(page))
        blocks = page.get_text("dict")["blocks"]
        has_images.append(any(b["type"] == 1 for b in blocks))

    # A page needs OCR if it has image blocks (scanned content) OR if its
    # text layer yields less than the minimum threshold. Pages that are
    # purely text-layer (no images, enough chars) skip OCR entirely.
    needs_ocr: list[int] = [
        i for i in range(n_pages)
        if has_images[i]
        or len(pymupdf_pages[i].strip()) < _PAGE_TEXT_MIN
        or is_garbled(pymupdf_pages[i])
    ]
    text_count = n_pages - len(needs_ocr)
    logger.info("[PDF] pymupdf_only=%d  needs_ocr=%d  (image_pages=%d  garbled_pages=%d)",
                text_count, len(needs_ocr), sum(has_images),
                sum(1 for i in range(n_pages) if is_garbled(pymupdf_pages[i])))

    # Text page confidence — use text_confidence() for quality of text layer
    text_page_confs: dict[int, float] = {}
    for i in range(n_pages):
        if i not in needs_ocr:
            text_page_confs[i] = text_confidence(pymupdf_pages[i])

    # Second pass: OCR only the pages that need it.
    ocr_results: dict[int, str] = {}
    ocr_page_confs: dict[int, float] = {}
    if needs_ocr:
        pipeline_t0 = time.perf_counter()
        futures: list[tuple[int, Future]] = []
        with ThreadPoolExecutor(max_workers=_OCR_WORKERS) as pool:
            for i in needs_ocr:
                arr = _render_page(doc, i, _DPI)
                fut = pool.submit(_timed_ocr_page, i, n_pages, arr, 50, langs, pipeline_t0)
                futures.append((i, fut))
        for i, fut in futures:
            text, source, conf = fut.result()
            ocr_results[i] = text
            ocr_page_confs[i] = conf if source != "none" else 0.0

    doc.close()

    # Merge: for image pages, combine PyMuPDF text layer + OCR so neither
    # loses content (e.g. title in text layer + body in scanned image).
    merged = []
    page_confs: list[float] = []
    for i in range(n_pages):
        if i not in ocr_results:
            merged.append(pymupdf_pages[i])
            page_confs.append(text_page_confs.get(i, 0.5))
        else:
            ocr_text = ocr_results[i]
            pdf_text = pymupdf_pages[i].strip()
            if pdf_text and pdf_text not in ocr_text:
                merged.append(pdf_text + "\n" + ocr_text)
            else:
                merged.append(ocr_text)
            page_confs.append(ocr_page_confs.get(i, 0.0))

    mean_conf = sum(page_confs) / len(page_confs) if page_confs else 0.0
    ocr_ratio = len(needs_ocr) / n_pages if n_pages else 0.0
    elapsed = time.perf_counter() - t0
    logger.info("[PDF] done  pymupdf=%d  ocr=%d  mean_conf=%.2f  total=%.1fs",
                text_count, len(needs_ocr), mean_conf, elapsed)

    return PdfResult(
        pages=_strip_repeated_lines(merged),
        ocr_ratio=ocr_ratio,
        mean_conf=mean_conf,
        total_pages=n_pages,
        ocr_pages=len(needs_ocr),
        text_pages=text_count,
        page_confs=page_confs,
    )


def _read_pdf_via_sidecar(filepath: str, source_url: str = "") -> PdfResult | None:
    """Use the Rust extraction sidecar when configured, falling back locally on error."""
    sidecar_url = os.getenv("EXTRACT_SIDECAR_URL", "").rstrip("/")
    if not sidecar_url:
        return None

    api_key = os.getenv("SIDECAR_API_KEY", "")
    if not api_key:
        logger.warning("[PDF] EXTRACT_SIDECAR_URL is set but SIDECAR_API_KEY is missing; using local reader")
        return None

    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {filepath}")

    try:
        preflight = _inspect_pdf_for_sidecar(path)
        force_sidecar = os.getenv("EXTRACT_SIDECAR_FORCE", "").lower() in {"1", "true", "yes"}
        if preflight["ocr_pages"] == 0 and not force_sidecar:
            logger.info("[PDF] pure text PDF detected; using local PyMuPDF fast path for %s", path.name)
            return None

        import httpx

        timeout = float(os.getenv("EXTRACT_SIDECAR_TIMEOUT_SECONDS", "180"))
        with path.open("rb") as fh:
            response = httpx.post(
                f"{sidecar_url}/extract-text",
                headers={"Authorization": f"Bearer {api_key}"},
                data={"source_url": source_url} if source_url else None,
                files={"file": (path.name, fh, "application/pdf")},
                timeout=timeout,
            )
        response.raise_for_status()
        payload = response.json()
        text = str(payload.get("text") or "")
        if not text.strip():
            logger.warning("[PDF] sidecar returned empty text for %s; using local reader", path.name)
            return None
        logger.info(
            "[PDF] sidecar extracted %s  cache_hit=%s  provider=%s",
            path.name,
            payload.get("cache_hit"),
            payload.get("ocr_provider"),
        )
        return PdfResult(
            pages=[text],
            ocr_ratio=preflight["ocr_ratio"],
            mean_conf=preflight["known_mean_conf"],
            total_pages=preflight["total_pages"],
            ocr_pages=preflight["ocr_pages"],
            text_pages=preflight["text_pages"],
            page_confs=preflight["page_confs"],
        )
    except Exception as exc:
        logger.warning("[PDF] sidecar extraction failed for %s: %s; using local reader", path.name, exc)
        return None


def _inspect_pdf_for_sidecar(path: Path) -> dict:
    """Return cheap per-page metadata before deciding whether to use sidecar."""
    doc = fitz.open(str(path))
    try:
        n_pages = len(doc)
        pymupdf_pages: list[str] = []
        has_images: list[bool] = []
        for page in doc:
            text = _extract_page_filtered(page)
            pymupdf_pages.append(text)
            blocks = page.get_text("dict")["blocks"]
            has_images.append(any(b["type"] == 1 for b in blocks))

        needs_ocr = [
            i for i in range(n_pages)
            if has_images[i]
            or len(pymupdf_pages[i].strip()) < _PAGE_TEXT_MIN
            or is_garbled(pymupdf_pages[i])
        ]
        text_page_confs = {
            i: text_confidence(pymupdf_pages[i])
            for i in range(n_pages)
            if i not in needs_ocr
        }
        page_confs = [
            text_page_confs.get(i, 0.0)
            for i in range(n_pages)
        ]
        known_mean_conf = sum(page_confs) / n_pages if n_pages else 0.0
        return {
            "total_pages": n_pages,
            "ocr_pages": len(needs_ocr),
            "text_pages": n_pages - len(needs_ocr),
            "ocr_ratio": len(needs_ocr) / n_pages if n_pages else 0.0,
            "known_mean_conf": known_mean_conf,
            "page_confs": page_confs,
        }
    finally:
        doc.close()


def extract_sections(filepath: str, min_section_chars: int = 100) -> list[dict]:
    """Extract document sections with page metadata, per-page routing."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {filepath}")

    if is_pure_text_pdf(filepath):
        # Quick garbled check on first page before committing to pure-text path
        doc = fitz.open(filepath)
        first_page_text = _extract_page_filtered(doc[0])
        doc.close()
        if is_garbled(first_page_text):
            logger.info("[PDF] garbled font encoding detected — routing to OCR")
            return extract_sections_ocr(filepath, min_section_chars)
        return extract_sections_pure(filepath, min_section_chars)
    else:
        return extract_sections_ocr(filepath, min_section_chars)


def get_pdf_type(filepath: str) -> str:
    """Return 'pure_text', 'scanned', or 'mixed' for the given PDF."""
    path = Path(filepath)
    doc = fitz.open(str(path))
    pymupdf_pages = [_extract_page_filtered(page) for page in doc]
    doc.close()
    text_pages = sum(1 for t in pymupdf_pages if len(t.strip()) >= _PAGE_TEXT_MIN)
    if text_pages == len(pymupdf_pages):
        return "pure_text"
    if text_pages == 0:
        return "scanned"
    return "mixed"
