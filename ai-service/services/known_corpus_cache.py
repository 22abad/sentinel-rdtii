"""Local fallback cache of the KNOWN baseline laws (``data/known_corpus/``).

During a live run the pipeline fetches each candidate's text from its official
source, and ``document_fetch`` already falls back to the Wayback Machine and
Google Cache when that source is unreachable ("works like a human"). This module
is the *last* line of defence: if even those archives fail, serve the
pre-downloaded text for that URL from the local KNOWN-baseline corpus so an
official baseline law is never silently missed during judging.

The corpus (`data/known_corpus/manifest.jsonl`) holds ~200 baseline laws for the
three provided economies with their source URL and a cached text file; this
module indexes it by URL and hands back the text.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_MANIFEST = _REPO / "data" / "known_corpus" / "manifest.jsonl"
_MIN_USABLE = 400  # a real statute body, not a stub/error page


@functools.lru_cache(maxsize=1)
def _url_index() -> dict[str, str]:
    """``{source_url: absolute text_path}`` for entries whose text file exists."""
    index: dict[str, str] = {}
    if not _MANIFEST.exists():
        return index
    for line in _MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:  # noqa: BLE001 — a malformed line must not break the run
            continue
        url = (rec.get("url") or "").strip()
        text_path = rec.get("text_path") or ""
        if not url or not text_path:
            continue
        path = Path(text_path)
        if not path.is_absolute():
            path = _REPO / text_path
        if path.exists():
            index[url] = str(path)
    return index


def cached_text_for_url(url: str) -> str | None:
    """Return the pre-downloaded KNOWN-baseline text for ``url``, or ``None``.

    ``None`` when the URL is not in the corpus or its cached text is too short to
    be a usable statute body — the caller then keeps its own (failed) result.
    """
    if not url:
        return None
    text_path = _url_index().get(url.strip())
    if not text_path:
        return None
    try:
        text = Path(text_path).read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return None
    return text if len(text.strip()) >= _MIN_USABLE else None


def corpus_size() -> int:
    """How many URLs have a cached text file on disk (for logging/diagnostics).

    A per-URL length gate still applies at read time in ``cached_text_for_url``.
    """
    return len(_url_index())
