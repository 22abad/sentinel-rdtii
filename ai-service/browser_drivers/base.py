from __future__ import annotations

from typing import Any, Literal, Protocol


BrowserMode = Literal["auto", "playwright", "opencli"]


class BrowserFetchError(RuntimeError):
    """Raised when a browser backend cannot fetch a URL."""


def normalize_browser_mode(value: str | None) -> BrowserMode:
    mode = (value or "auto").strip().lower()
    if mode in {"auto", "playwright", "opencli"}:
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
