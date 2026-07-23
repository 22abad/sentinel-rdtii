from __future__ import annotations

from typing import Any, Literal, Protocol


# "http" = HTTP-only (curl_cffi impersonation + plain HTTP), NEVER launch a
# browser. Batch corpus tools (restore_corpus/refetch_statutes) use it: the
# Playwright rung intermittently segfaults the driver under load (macOS "Python
# quit unexpectedly"), and for the blocked portals it wouldn't beat curl_cffi
# anyway — so http-mode fails fast instead of crashing.
BrowserMode = Literal["auto", "playwright", "opencli", "http"]


class BrowserFetchError(RuntimeError):
    """Raised when a browser backend cannot fetch a URL."""


def normalize_browser_mode(value: str | None) -> BrowserMode:
    mode = (value or "auto").strip().lower()
    if mode in {"auto", "playwright", "opencli", "http"}:
        return mode  # type: ignore[return-value]
    return "auto"


class BrowserDriver(Protocol):
    async def fetch_legal_content(
        self,
        url: str,
        *,
        timeout: int = 60000,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Fetch rendered or downloadable legal content."""
