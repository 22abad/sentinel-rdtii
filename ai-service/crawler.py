from __future__ import annotations

from legal_crawler import browser as _browser
from legal_crawler import fallbacks as _fallbacks
from legal_crawler import fetcher as _fetcher
from legal_crawler import ocs as _ocs
from legal_crawler import timeline as _timeline
from legal_crawler import wayback as _wayback
from legal_crawler.constants import DOWNLOADS_DIR, INVALID_URL_PATTERNS, KNOWN_ALTERNATIVES

async_playwright = _browser.async_playwright
_ORIGINAL_FETCH_WAYBACK_CLOSEST = _wayback.fetch_wayback_closest
_ORIGINAL_FETCH_WAYBACK_CONTENT = _wayback.fetch_wayback_content
_ORIGINAL_FETCH_GOOGLE_CACHE = _wayback.fetch_google_cache

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


def _patched_or_original(current, facade, original):
    return original if current is facade else current


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
    _wayback.fetch_wayback_closest = _patched_or_original(
        fetch_wayback_closest,
        _fetch_wayback_closest_facade,
        _ORIGINAL_FETCH_WAYBACK_CLOSEST,
    )

    _timeline.fetch_wayback_closest = _patched_or_original(
        fetch_wayback_closest,
        _fetch_wayback_closest_facade,
        _ORIGINAL_FETCH_WAYBACK_CLOSEST,
    )

    _fallbacks._precheck_url = _precheck_url
    _fallbacks._try_http_fallback = _try_http_fallback
    _fallbacks._try_wayback_fallback = _try_wayback_fallback
    _fallbacks._try_opencli_fetch = _try_opencli_fetch
    _fallbacks.fetch_wayback_content = _patched_or_original(
        fetch_wayback_content,
        _fetch_wayback_content_facade,
        _ORIGINAL_FETCH_WAYBACK_CONTENT,
    )

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
    _fetcher.fetch_wayback_content = _patched_or_original(
        fetch_wayback_content,
        _fetch_wayback_content_facade,
        _ORIGINAL_FETCH_WAYBACK_CONTENT,
    )
    _fetcher.fetch_google_cache = _patched_or_original(
        fetch_google_cache,
        _fetch_google_cache_facade,
        _ORIGINAL_FETCH_GOOGLE_CACHE,
    )


async def search_ocs_law(*args, **kwargs):
    _sync_patch_points()
    return await _ocs.search_ocs_law(*args, **kwargs)


async def fetch_ocs_law_document(*args, **kwargs):
    _sync_patch_points()
    return await _ocs.fetch_ocs_law_document(*args, **kwargs)


async def fetch_thai_law_by_keyword(*args, **kwargs):
    _sync_patch_points()
    return await _ocs.fetch_thai_law_by_keyword(*args, **kwargs)


async def fetch_wayback_closest(*args, **kwargs):
    _sync_patch_points()
    return await _ORIGINAL_FETCH_WAYBACK_CLOSEST(*args, **kwargs)


async def fetch_wayback_content(*args, **kwargs):
    _sync_patch_points()
    return await _ORIGINAL_FETCH_WAYBACK_CONTENT(*args, **kwargs)


async def fetch_google_cache(*args, **kwargs):
    _sync_patch_points()
    return await _ORIGINAL_FETCH_GOOGLE_CACHE(*args, **kwargs)


_fetch_wayback_closest_facade = fetch_wayback_closest
_fetch_wayback_content_facade = fetch_wayback_content
_fetch_google_cache_facade = fetch_google_cache


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
