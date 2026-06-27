from __future__ import annotations

from legal_crawler import browser as _browser
from legal_crawler import fallbacks as _fallbacks
from legal_crawler import fetcher as _fetcher
from legal_crawler import ocs as _ocs
from legal_crawler import timeline as _timeline
from legal_crawler import wayback as _wayback
from legal_crawler.constants import DOWNLOADS_DIR, INVALID_URL_PATTERNS, KNOWN_ALTERNATIVES

async_playwright = _browser.async_playwright

_apply_stealth = _browser._apply_stealth
_initialize_browser_context = _browser._initialize_browser_context
_wait_for_page_load = _browser._wait_for_page_load
_download_file = _browser._download_file
_read_docx = _browser._read_docx
_extract_html_content = _browser._extract_html_content

_precheck_url = _fallbacks._precheck_url
_try_http_fallback = _fallbacks._try_http_fallback
_try_wayback_fallback = _fallbacks._try_wayback_fallback
_try_opencli_fetch = _fallbacks._try_opencli_fetch

fetch_wayback_closest = _wayback.fetch_wayback_closest
fetch_wayback_content = _wayback.fetch_wayback_content
fetch_google_cache = _wayback.fetch_google_cache


def _sync_patch_points() -> None:
    _browser.async_playwright = async_playwright
    _ocs.async_playwright = async_playwright
    _wayback.async_playwright = async_playwright
    _fetcher.async_playwright = async_playwright

    _browser._apply_stealth = _apply_stealth
    _browser._initialize_browser_context = _initialize_browser_context
    _browser._wait_for_page_load = _wait_for_page_load
    _browser._download_file = _download_file
    _browser._read_docx = _read_docx
    _browser._extract_html_content = _extract_html_content

    _ocs._apply_stealth = _apply_stealth
    _ocs._initialize_browser_context = _initialize_browser_context

    _wayback._apply_stealth = _apply_stealth
    _wayback._initialize_browser_context = _initialize_browser_context
    _wayback.fetch_wayback_closest = fetch_wayback_closest

    _timeline.fetch_wayback_closest = fetch_wayback_closest

    _fallbacks._precheck_url = _precheck_url
    _fallbacks._try_http_fallback = _try_http_fallback
    _fallbacks._try_wayback_fallback = _try_wayback_fallback
    _fallbacks._try_opencli_fetch = _try_opencli_fetch
    _fallbacks.fetch_wayback_content = fetch_wayback_content

    _fetcher._apply_stealth = _apply_stealth
    _fetcher._initialize_browser_context = _initialize_browser_context
    _fetcher._wait_for_page_load = _wait_for_page_load
    _fetcher._download_file = _download_file
    _fetcher._read_docx = _read_docx
    _fetcher._extract_html_content = _extract_html_content
    _fetcher._precheck_url = _precheck_url
    _fetcher._try_http_fallback = _try_http_fallback
    _fetcher._try_wayback_fallback = _try_wayback_fallback
    _fetcher._try_opencli_fetch = _try_opencli_fetch
    _fetcher.fetch_thai_law_by_keyword = fetch_thai_law_by_keyword
    _fetcher.fetch_wayback_content = fetch_wayback_content
    _fetcher.fetch_google_cache = fetch_google_cache


async def search_ocs_law(*args, **kwargs):
    _sync_patch_points()
    return await _ocs.search_ocs_law(*args, **kwargs)


async def fetch_ocs_law_document(*args, **kwargs):
    _sync_patch_points()
    return await _ocs.fetch_ocs_law_document(*args, **kwargs)


async def fetch_thai_law_by_keyword(*args, **kwargs):
    _sync_patch_points()
    return await _ocs.fetch_thai_law_by_keyword(*args, **kwargs)


async def verify_law_timeline(*args, **kwargs):
    _sync_patch_points()
    return await _timeline.verify_law_timeline(*args, **kwargs)


async def fetch_legal_content(*args, **kwargs):
    _sync_patch_points()
    return await _fetcher.fetch_legal_content(*args, **kwargs)


async def crawl_for_pdpa_pdf(*args, **kwargs):
    _sync_patch_points()
    return await _fetcher.crawl_for_pdpa_pdf(*args, **kwargs)


__all__ = [
    "DOWNLOADS_DIR",
    "INVALID_URL_PATTERNS",
    "KNOWN_ALTERNATIVES",
    "async_playwright",
    "search_ocs_law",
    "fetch_ocs_law_document",
    "fetch_thai_law_by_keyword",
    "fetch_wayback_closest",
    "fetch_wayback_content",
    "fetch_google_cache",
    "verify_law_timeline",
    "fetch_legal_content",
    "crawl_for_pdpa_pdf",
]
