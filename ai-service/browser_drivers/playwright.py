from __future__ import annotations

from typing import Any


class PlaywrightBrowserDriver:
    """Adapter for the existing Playwright crawler implementation.

    The Playwright code still lives in ``crawler.py`` for now because it also
    owns PDF/Word downloads, Wayback fallback, and country-specific legal-source
    fallbacks. This adapter gives the rest of the app a driver-shaped entry
    point without doing a risky large-file move.
    """

    async def fetch_legal_content(
        self,
        url: str,
        *,
        timeout: int = 60000,
        max_retries: int = 3,
        proxy: dict | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        from crawler import fetch_legal_content

        return await fetch_legal_content(
            url,
            timeout=timeout,
            max_retries=max_retries,
            proxy=proxy,
            browser_mode="playwright",
        )
