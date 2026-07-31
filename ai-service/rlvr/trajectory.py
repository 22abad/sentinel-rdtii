"""Append-only JSONL of every sampled candidate.

Write-only and side-effect-free with respect to the pipeline: nothing reads
this file back during a run. That is deliberate — it can be switched on for a
full submission run without changing a single output row, and it is the one
piece of this whole seam that is safe to enable before a deadline.

One record per (document, chunk, indicator, sample). A later RFT/GRPO run
filters on ``proxy.total`` (and ``oracle.total`` where a reviewed case exists)
to build its training set, so the record carries the full breakdown rather
than a single scalar — a reward you cannot decompose later is a reward you
cannot debug.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


@dataclass
class TrajectoryWriter:
    """Thread-safe JSONL appender.

    The pipeline runs chunk groups under ``asyncio.gather`` with a semaphore,
    so writes genuinely interleave; a plain ``open(..., "a")`` per record would
    risk torn lines under CPython's buffering.
    """

    path: Path
    run_id: str
    provider: str = "unknown"
    model: str = "unknown"
    enabled: bool = True

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._count = 0
        if self.enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def records_written(self) -> int:
        return self._count

    def log_candidate(
        self,
        *,
        document_id: str,
        chunk_index: int,
        indicator_id: str,
        sampling: dict[str, Any],
        candidate: dict[str, Any],
        proxy: dict[str, Any],
        selected: bool,
        country_code: str = "",
        oracle: dict[str, Any] | None = None,
        fingerprint: str = "",
    ) -> None:
        if not self.enabled:
            return
        record = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "logged_at": datetime.now(timezone.utc).isoformat(),
            "provider": self.provider,
            "model": self.model,
            "country_code": country_code,
            "document_id": document_id,
            "chunk_index": chunk_index,
            "indicator_id": indicator_id,
            "sampling": sampling,
            "fingerprint": fingerprint,
            # Only the fields a training run needs. The full chunk text is
            # deliberately excluded — it is recoverable from the corpus by
            # (document_id, chunk_index) and would multiply the file size by
            # the sample count for no gain.
            "candidate": {
                "verbatim_quote": candidate.get("verbatim_quote", ""),
                "article_clause": candidate.get("article_clause", ""),
                "source_legislation": candidate.get("source_legislation", ""),
                "source_url": candidate.get("source_url", ""),
                "last_update": candidate.get("last_update", ""),
                "scope": candidate.get("scope", ""),
            },
            "proxy": proxy,
            "oracle": oracle,
            "selected": selected,
        }
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            self._count += 1



__all__ = ["SCHEMA_VERSION", "TrajectoryWriter"]
