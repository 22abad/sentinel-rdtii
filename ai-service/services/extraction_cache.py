"""Extraction cache — never run the LLM twice on the same content.

Keyed by the SHA-256 of the exact source text. On a cache hit the full
extraction response is returned verbatim, so a document that was already
processed (by this user or a teammate, in this session or a previous one) is
served from the cache instead of paying for another LLM extraction — the
"素材入库、避免重复劳动" (accumulated material is reused, never re-done) vision.

This sits at the DOCUMENT level and complements two neighbours:
  - canvas_file_ingest dedups the raw UPLOAD (don't re-store the same file);
  - evidence_store banks reviewed MAPPINGS (the reusable evidence baseline);
  - this caches the EXTRACTION (don't re-run the LLM on identical text).

Best-effort throughout: with no database (e.g. the judge CLI) every call is a
silent no-op, so extraction proceeds normally and nothing breaks.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from auth import _db_connect

logger = logging.getLogger(__name__)


# Fold the pipeline generation into the cache key: entries written by an
# older gate/classifier generation must never be served again (a pre-fix run
# once served a heading-quote 7.1 row scored 1, instantly, into the audit
# panel). Bump whenever extraction/gate behaviour changes materially — old
# rows simply stop matching; no migration needed.
CACHE_SCHEMA_VERSION = "2026-07-19-gates-v2"


def source_hash(text: str) -> str:
    """Stable content fingerprint. Whitespace-normalised so trivially-different
    copies of the same document (extra blank lines, trailing spaces) still hit."""
    normalized = "\n".join(line.rstrip() for line in (text or "").strip().splitlines())
    return hashlib.sha256(
        f"{CACHE_SCHEMA_VERSION}\n{normalized}".encode("utf-8")
    ).hexdigest()


def get_cached(text: str) -> dict[str, Any] | None:
    """Return the cached extraction response for this exact content, or None.

    None means "no cache / no database" — the caller should extract normally.
    """
    if not (text or "").strip():
        return None
    digest = source_hash(text)
    conn = None
    try:
        conn = _db_connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT response FROM extraction_cache WHERE source_sha256 = %s",
            (digest,),
        )
        row = cur.fetchone()
        cur.close()
        if not row:
            return None
        response = row[0]
        # psycopg2 returns JSONB as a dict already; tolerate a text column too.
        if isinstance(response, str):
            response = json.loads(response)
        return response if isinstance(response, dict) else None
    except Exception:  # noqa: BLE001 — a cache miss must never break extraction
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def put_cached(text: str, response: dict[str, Any], *, provider: str | None = None) -> bool:
    """Store the extraction response under this content's fingerprint.

    Idempotent (ON CONFLICT DO NOTHING). Returns True if a row was written,
    False on a duplicate or any best-effort failure.
    """
    if not (text or "").strip() or not isinstance(response, dict):
        return False
    digest = source_hash(text)
    conn = None
    try:
        conn = _db_connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO extraction_cache (source_sha256, response, provider) "
            "VALUES (%s, %s, %s) ON CONFLICT (source_sha256) DO NOTHING",
            (digest, json.dumps(response), provider),
        )
        written = cur.rowcount > 0
        conn.commit()
        cur.close()
        return written
    except Exception:  # noqa: BLE001 — caching is best-effort
        if conn is not None:
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
