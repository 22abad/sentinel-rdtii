"""The judge-validated 13-field submission contract.

Column order is frozen: judges validate programmatically and reject renamed or
reordered columns. Do not change ``CSV_COLUMNS`` without confirming against the
official README template.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

# ── Frozen 13-column CSV contract (exact order) ──────────────────────────────
# Source: requirements/README_template.md → "Output Format" table.
CSV_COLUMNS: tuple[str, ...] = (
    "economy",           # 1  Official UN country name
    "law_name",          # 2  Full official statute name and year
    "law_number_ref",    # 3  Official act/law number (e.g. Act 709, B.E. 2562)
    "last_amended",      # 4  Year of most recent amendment; blank if never amended
    "indicator_id",      # 5  RDTII code (e.g. P6-I1, P7-I3)
    "article",           # 6  Exact article and paragraph (e.g. Art. 26(2))
    "discovery_tag",     # 7  NEW = independent find; KNOWN = sample kit
    "location_reference",# 8  PDF: page number; HTML: URL anchor or section path
    "verbatim_snippet",  # 9  Exact quoted text — no paraphrasing
    "mapping_rationale", # 10 Max 300 chars: why this provision maps to this indicator
    "source_url",        # 11 Direct URL to law on official government portal
    "confidence",        # 12 Model certainty score (0.00–1.00)
    "notes",             # 13 OCR issues, partial doc, bilingual sources, cross-refs
)

# Extended metadata written only to the JSON output (not the CSV).
JSON_EXTENDED_FIELDS: tuple[str, ...] = (
    "novelty_type",
    "canonical_law_id",
    "amendment_version_date",
    "normalized_article",
    "normalized_quote_hash",
    "ocr_quality_cer",
    "processing_time_seconds",
    "raw_context_before",
    "raw_context_after",
    "pdf_is_scanned",
    "retrieval_method",
    "retrieval_mode",
    "final_url",
    "http_status",
    "fetch_method",
    "model_version",
    "source_file_sha256",
    "source_pdf_path",
    "pdf_type",
    "confidence_type",
)

MAPPING_RATIONALE_MAX = 300

# These fields are required for every provision to be useful to the judges'
# automated evaluator. Other frozen-schema columns may legitimately be blank.
# Fields a row MUST have to be judge-usable. 'article' is deliberately NOT
# here: it is best-effort (backfilled by infer_article_reference), the official
# CSV schema only requires the column to exist, and a few unlocatable headings
# must never suppress an otherwise-complete submission.
REQUIRED_SUBMISSION_FIELDS: tuple[str, ...] = (
    "law_name",
    "indicator_id",
    "verbatim_snippet",
    "source_url",
)

# Official UN economy names keyed by ISO-3166 alpha-3 code.
# Display names follow the Round 2 database sheet names so outputs join
# cleanly against the official baseline.
ECONOMY_NAMES: dict[str, str] = {
    "SGP": "Singapore",
    "MYS": "Malaysia",
    "AUS": "Australia",
    "CHN": "China",
    "THA": "Thailand",
    "IND": "India",
    "IDN": "Indonesia",
    "LAO": "Lao PDR",
    "MNG": "Mongolia",
    "RUS": "Russian Federation",
    "NIU": "Niue",
}

# Reverse lookup accepting common spellings/casing.
_NAME_TO_CODE: dict[str, str] = {name.lower(): code for code, name in ECONOMY_NAMES.items()}
_NAME_TO_CODE.update({code.lower(): code for code in ECONOMY_NAMES})
_NAME_TO_CODE.update({
    "laos": "LAO",
    "lao people's democratic republic": "LAO",
    "russia": "RUS",
})


def economy_code(economy: str) -> str:
    """Resolve an economy name or ISO code to an ISO-3 code (upper-case).

    Accepts "Singapore", "singapore", "SGP", or "sgp". Raises for unknown input
    so the CLI can fail fast with a clear message instead of silently mislabeling.
    """

    key = economy.strip().lower()
    if key in _NAME_TO_CODE:
        return _NAME_TO_CODE[key]
    raise ValueError(
        f"Unknown economy {economy!r}. Supported: "
        + ", ".join(sorted(ECONOMY_NAMES.values()))
    )


def economy_display_name(economy: str) -> str:
    """Return the official UN display name for an economy name or code."""

    return ECONOMY_NAMES[economy_code(economy)]


def indicator_to_rdtii_code(indicator: str) -> str:
    """Convert an internal indicator id to the judges' RDTII code.

    "6.1" -> "P6-I1", "7.3" -> "P7-I3", "4.10" -> "P4-I10", and sub-indicators
    keep their dotted tail: "12.4.1" -> "P12-I4.1". Input already in "Pn-Im"
    form is returned unchanged.
    """

    indicator = indicator.strip()
    if re.fullmatch(r"P\d+-I\d+(\.\d+)?", indicator):
        return indicator
    match = re.fullmatch(r"(\d+)\.(\d+(?:\.\d+)?)", indicator)
    if not match:
        raise ValueError(f"Cannot convert indicator id {indicator!r} to RDTII code.")
    pillar, index = match.group(1), match.group(2)
    return f"P{pillar}-I{index}"


def discovery_tag_for_method(discovery_method: str) -> str:
    """Map a discovery ``discovery_method`` to the NEW/KNOWN submission tag.

    "known_mapping" means the candidate came from a curated known-law mapping
    (the sample kit); anything else (cached_discovery, official_search,
    web_search, ...) is an independent find.
    """

    return (
        "KNOWN"
        if discovery_method.strip().lower() in {"known_mapping", "fixture", "fallback"}
        else "NEW"
    )


# Law-number patterns in priority order. A bare "Act <4-digit-year>" is the
# title year (e.g. "Companies Act 2016"), NOT the official number, so the
# generic Act pattern deliberately excludes 4-digit years and prefers a
# parenthesised number like "(Act 777)".
_LAW_NUMBER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\(\s*(Act\s+[A-Z]?\d+)\s*\)", re.IGNORECASE),   # (Act 777), (Act A1727)
    re.compile(r"(B\.E\.\s*\d{4})", re.IGNORECASE),               # B.E. 2562
    re.compile(r"(No\.\s*\d+\s+of\s+\d{4})", re.IGNORECASE),      # No. 26 of 2018
    re.compile(r"(Cap\.\s*\d+)", re.IGNORECASE),                  # Cap. 50
    re.compile(r"(Act\s+[A-Z]\d+)", re.IGNORECASE),               # Act A1727
    re.compile(r"(Act\s+\d{1,3})\b", re.IGNORECASE),              # Act 777 (not a year)
)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def extract_law_number_ref(law_name: str, fallback: str = "") -> str:
    """Best-effort official act/law number pulled from the law title."""

    for pattern in _LAW_NUMBER_PATTERNS:
        match = pattern.search(law_name or "")
        if match:
            return match.group(1).strip()
    return fallback.strip()


def extract_year(*values: str) -> str:
    """Return the last 4-digit year found across the given strings, else ''."""

    for value in values:
        matches = _YEAR_RE.findall(value or "")
        if matches:
            # findall returns the captured group prefixes; re-scan for full years.
            years = _YEAR_RE.finditer(value or "")
            last = None
            for m in years:
                last = m.group(0)
            if last:
                return last
    return ""


class SubmissionRow(BaseModel):
    """One provision → indicator mapping in the judges' 13-field contract.

    Every field is a string except ``confidence`` (float) so CSV output is
    unambiguous. Optional fields default to empty. Extended fields are written
    to JSON only.
    """

    economy: str
    law_name: str
    law_number_ref: str = ""
    last_amended: str = ""
    indicator_id: str
    article: str = ""
    discovery_tag: str = "NEW"
    location_reference: str = ""
    verbatim_snippet: str
    mapping_rationale: str = ""
    source_url: str = ""
    confidence: float = 0.0
    notes: str = ""

    # Extended metadata (JSON only)
    novelty_type: Literal["KNOWN", "NEW_LAW", "NEW_AMENDMENT", "NEW_PROVISION"] = "NEW_LAW"
    canonical_law_id: str = ""
    amendment_version_date: str = ""
    normalized_article: str = ""
    normalized_quote_hash: str = ""
    ocr_quality_cer: float | None = None
    processing_time_seconds: float | None = None
    raw_context_before: str = ""
    raw_context_after: str = ""
    pdf_is_scanned: bool | None = None
    retrieval_method: str = ""
    retrieval_mode: str = "unknown"
    final_url: str = ""
    http_status: int | None = None
    fetch_method: str = ""
    model_version: str = ""
    source_file_sha256: str = ""
    source_pdf_path: str = ""
    pdf_type: Literal[
        "scanned", "mixed", "pure_text", "not_pdf", "unknown"
    ] = "unknown"
    confidence_type: Literal["discovery_confidence", "not_available"] = "not_available"

    def csv_record(self) -> dict[str, str]:
        """Return an ordered dict of exactly the 13 CSV columns as strings."""

        record = {}
        for column in CSV_COLUMNS:
            value = getattr(self, column)
            if column == "confidence":
                record[column] = f"{float(value):.2f}"
            else:
                record[column] = "" if value is None else str(value)
        return record

    def json_record(self) -> dict:
        """Return the 13 CSV columns plus the extended JSON-only metadata."""

        record: dict = {}
        for column in CSV_COLUMNS:
            record[column] = getattr(self, column)
        for field in JSON_EXTENDED_FIELDS:
            record[field] = getattr(self, field)
        return record

    @classmethod
    def clip_rationale(cls, text: str) -> str:
        """Trim a rationale to the 300-char contract limit on a word boundary."""

        text = " ".join((text or "").split())
        if len(text) <= MAPPING_RATIONALE_MAX:
            return text
        clipped = text[:MAPPING_RATIONALE_MAX].rsplit(" ", 1)[0]
        return clipped.rstrip() + "…"


def validate_submission_rows(
    rows: list[SubmissionRow],
    *,
    allow_empty: bool = False,
) -> list[SubmissionRow]:
    """Return the judge-usable rows, dropping incomplete ones with a warning.

    A row missing a judge-critical field (source, quote, law, indicator) is
    dropped rather than allowed to suppress the whole submission — a single
    bad row must never leave a judge with zero output files. Raises only when
    NO usable row remains (unless ``allow_empty``).
    """
    import logging

    logger = logging.getLogger(__name__)

    valid: list[SubmissionRow] = []
    for index, row in enumerate(rows, start=1):
        missing = [
            field
            for field in REQUIRED_SUBMISSION_FIELDS
            if not str(getattr(row, field, "") or "").strip()
        ]
        if missing:
            logger.warning(
                "Dropping incomplete submission row %d (missing: %s)",
                index, ", ".join(missing),
            )
            continue
        valid.append(row)

    if not valid and not allow_empty:
        raise ValueError(
            "No judge-usable provisions were produced (all rows were empty or "
            "incomplete). No output files were written. Check the provider/API "
            "key and network, try --pdf, or use --allow-empty for research runs."
        )
    return valid
