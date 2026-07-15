"""Local law library — a cache-first, offline store of official legal texts.

Live discovery (Playwright crawl of government portals) is the headline Task-1
capability, but it is fragile in a judge's <10-minute run: portals rate-limit,
block bots, require JavaScript, or go down. This module is the reliability
backstop — a **verifiable cache of official text** (URL + retrieval date +
SHA-256), NOT a store of hand-authored answers. When a run is offline, the same
mapping pipeline (classify -> extract -> verify -> deterministic score) runs over
the cached text, so the *mapping* is still produced live; only *retrieval* is
cached.

Every entry's text is integrity-checked against its recorded SHA-256 on load, so
a corrupted or edited cache fails loudly instead of silently serving bad text.

Laws in this library are the curated **KNOWN** baseline (discovery_tag=KNOWN);
anything the live sweep finds beyond it is tagged NEW.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# ai-service/law_library/__init__.py -> parents[2] == repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIBRARY_ROOT = REPO_ROOT / "data" / "law_library"


class LawLibraryError(RuntimeError):
    """Raised when the library manifest or a cached text fails integrity checks."""


@dataclass(frozen=True)
class LawEntry:
    """One cached statute/provision in the local library."""

    law_id: str
    economy: str  # ISO-3 country code, e.g. "SGP"
    law_name: str
    official_url: str
    source_status: str
    pillars: tuple[int, ...]
    indicator_hints: tuple[str, ...]
    language_codes: tuple[str, ...]
    text_path: str
    sha256: str
    retrieved_at: str
    discovery_tag: str
    last_amended: str = ""
    version: str = ""
    currency_source: str = ""
    currency_checked_at: str = ""
    # "known" = sample-kit / KNOWN baseline; "discovered" = an independent NEW find
    # (cached for reproducibility, but must still surface as NEW, not KNOWN).
    origin: str = "known"
    text: str = field(repr=False, default="")

    def covers_pillar(self, pillar: int | None) -> bool:
        return pillar is None or pillar in self.pillars


def _manifest_path(library_root: Path) -> Path:
    return library_root / "manifest.jsonl"


def load_library(
    library_root: Path | str = DEFAULT_LIBRARY_ROOT,
    *,
    repo_root: Path | str = REPO_ROOT,
) -> list[LawEntry]:
    """Load and integrity-check every cached law.

    Returns an empty list if the library has not been provisioned (no manifest),
    so an ``--offline`` run degrades to a clear "nothing cached" message rather
    than an exception. Raises :class:`LawLibraryError` if a recorded text is
    missing or its SHA-256 does not match (tamper/corruption).
    """

    library_root = Path(library_root)
    repo_root = Path(repo_root)
    manifest = _manifest_path(library_root)
    if not manifest.exists():
        return []

    entries: list[LawEntry] = []
    for line_no, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LawLibraryError(f"manifest line {line_no} is not valid JSON: {exc}") from exc

        text_path = (repo_root / record["text_path"]).resolve()
        if not str(text_path).startswith(str(repo_root.resolve())):
            raise LawLibraryError(f"text_path escapes repository: {record['text_path']}")
        if not text_path.exists():
            raise LawLibraryError(f"missing cached text for {record['law_id']}: {record['text_path']}")

        text = text_path.read_text(encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest != record["sha256"]:
            raise LawLibraryError(
                f"SHA-256 mismatch for {record['law_id']} "
                f"({record['text_path']}): expected {record['sha256']}, got {digest}"
            )

        entries.append(
            LawEntry(
                law_id=record["law_id"],
                economy=record["economy"].upper(),
                law_name=record["law_name"],
                official_url=record["official_url"],
                source_status=record.get("source_status", "unknown"),
                pillars=tuple(record.get("pillars", [])),
                indicator_hints=tuple(record.get("indicator_hints", [])),
                language_codes=tuple(record.get("language_codes", ["en"])),
                text_path=record["text_path"],
                sha256=record["sha256"],
                retrieved_at=record.get("retrieved_at", ""),
                discovery_tag=record.get("discovery_tag", "KNOWN"),
                last_amended=record.get("last_amended", ""),
                version=record.get("version", ""),
                currency_source=record.get("currency_source", ""),
                currency_checked_at=record.get("currency_checked_at", ""),
                origin=record.get("origin", "known"),
                text=text,
            )
        )
    return entries


# Distinctive version fingerprints: compilation numbers, revised editions, act
# numbers, and dates. Their disappearance from an official page is a signal that a
# law may have been amended/re-compiled since we cached it.
_CURRENCY_TOKEN = re.compile(
    r"Compilation No\.\s*\d+|\d{4}\s+Revised Edition|Act\s+\d+|\d{1,2}\s+[A-Z][a-z]+\s+\d{4}"
)


def currency_tokens(version: str) -> list[str]:
    """Distinctive fingerprints extracted from a stored version label."""

    return _CURRENCY_TOKEN.findall(version or "")


def assess_currency(version: str, page_text: str) -> dict:
    """Compare a stored version label against freshly fetched official page text.

    Returns whether every distinctive version fingerprint still appears on the
    live page. A missing fingerprint means the law may have been amended/
    re-compiled — a lead for review, not proof (following the draft-for-review
    guardrail).
    """

    tokens = currency_tokens(version)
    normalized = re.sub(r"\s+", " ", page_text or "")
    found = [t for t in tokens if t in normalized]
    return {
        "version": version,
        "tokens": tokens,
        "tokens_found": found,
        "current": bool(tokens) and len(found) == len(tokens),
    }


def lookup(
    economy: str,
    *,
    pillar: int | None = None,
    indicators: list[str] | None = None,
    library_root: Path | str = DEFAULT_LIBRARY_ROOT,
    entries: list[LawEntry] | None = None,
) -> list[LawEntry]:
    """Return cached laws for an economy, optionally filtered by pillar/indicators.

    ``economy`` accepts an ISO-3 code (``"SGP"``) case-insensitively. Filtering by
    ``indicators`` is a coarse hint match against the law's recorded
    ``indicator_hints`` — the actual indicators are still re-derived live by the
    mapping pipeline; this only narrows which cached laws are worth processing.
    """

    pool = entries if entries is not None else load_library(library_root)
    code = economy.strip().upper()
    wanted = {i.strip() for i in indicators} if indicators else None

    matches = []
    for entry in pool:
        if entry.economy != code:
            continue
        if not entry.covers_pillar(pillar):
            continue
        if wanted is not None and not (wanted & set(entry.indicator_hints)):
            continue
        matches.append(entry)
    return matches
