"""The judge-validated 13-field submission contract.

Column order is frozen: judges validate programmatically and reject renamed or
reordered columns. Do not change ``CSV_COLUMNS`` without confirming against the
official README template.
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

# RDTII 2.1 "Non-regulatory indicators" (official framework doc): these are
# derived from EXTERNAL databases / treaty-membership checks (WITS tariffs,
# V-Dem shutdowns, WTO/WIPO/UNCITRAL participation), NOT from extracting a law —
# "an automated data retrieval method is not required". So a law-derived evidence
# row for one of these is misconceived and must not enter the submission. In
# Round-1 scope (P6/P7) the only one is 6.5 ("not in a binding data-transfer
# agreement"). Stored in the judges' "Pn-Im" code form used by indicator_id.
NON_REGULATORY_INDICATORS: frozenset[str] = frozenset({
    "P1-I1", "P1-I2", "P1-I3", "P2-I4", "P4-I4", "P4-I7", "P4-I8", "P5-I6",
    "P6-I5", "P9-I2", "P12-I10", "P12-I11", "P12-I12", "P12-I13",
})

# ── Frozen 13-column CSV contract (exact order) ──────────────────────────────
# Source: requirements/README_template.md → "Output Format" table.
CSV_COLUMNS: tuple[str, ...] = (
    "economy",           # 1  Official UN country name
    "law_name",          # 2  Full official statute name and year
    "law_number_ref",    # 3  Official act/law number (e.g. Act 709, B.E. 2562)
    "last_amended",      # 4  Year of most recent amendment; explicit unknown if unavailable
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

# The EXACT header row the judges validate against — the official
# "Structured Output Template" (OUTPUT_TEMPLATE_31MAY.xlsx): "Column names and
# order must match this template exactly. Judges validate programmatically."
# Title Case with spaces, same order as CSV_COLUMNS. The snake_case names above
# are the internal field keys; this is what gets written to the submission CSV.
CSV_HEADERS: tuple[str, ...] = (
    "Economy", "Law Name", "Law Number / Ref", "Last Amended", "Indicator ID",
    "Article / Section", "Discovery Tag", "Location Reference", "Verbatim Snippet",
    "Mapping Rationale", "Source URL", "Confidence", "Notes",
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
    "source_confidence",
    "mapping_decision",
    "mapping_confidence_type",
    "eligibility_evidence_spans",
    "eligibility_verifier_mode",
    "requires_human_review",
)

MAPPING_RATIONALE_MAX = 300

# These fields are required for every provision to be useful to the judges'
# automated evaluator. Other frozen-schema columns may legitimately be blank.
# Fields a row MUST have to be judge-usable.  The official orientation rubric
# requires an exact article/paragraph and last-amended value. Location remains
# optional in the frozen schema, but build_row fills it whenever provenance is
# available.
REQUIRED_SUBMISSION_FIELDS: tuple[str, ...] = (
    "law_name",
    "last_amended",
    "indicator_id",
    "article",
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
    last_amended: str = "Not stated in source"
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
    confidence_type: Literal[
        "mapping_confidence", "human_review_approved", "not_available"
    ] = "not_available"
    source_confidence: float = 0.0
    mapping_decision: Literal["supported", "insufficient", "contradicted"] = "supported"
    mapping_confidence_type: str = "rule_based_eligibility"
    eligibility_evidence_spans: dict[str, list[str]] = Field(default_factory=dict)
    eligibility_verifier_mode: str = "deterministic"
    requires_human_review: bool = False

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


def cap_rows_per_law_indicator(
    rows: list["SubmissionRow"], *, cap: int = 10
) -> list["SubmissionRow"]:
    """Keep at most ``cap`` provisions per (law, indicator).

    A single statute run through extraction can surface dozens of clauses for
    the same indicator (the 173k-char QLD IP Act produced 42 rows for P7-I1);
    an indicator is established by its few strongest provisions, and the long
    tail reads as padding. Keeps the rows with the longest verbatim quote
    (proxy for a substantive provision), preserving original order among kept
    rows. Purely a submission-tidiness pass — it never fabricates or reorders
    output, only trims over-extraction.
    """
    if cap <= 0:
        return rows
    groups: dict[tuple[str, str], list[int]] = {}
    for i, row in enumerate(rows):
        law = " ".join((row.law_name or "").split()).casefold()
        groups.setdefault((law, row.indicator_id), []).append(i)
    keep: set[int] = set()
    for idxs in groups.values():
        if len(idxs) <= cap:
            keep.update(idxs)
            continue
        ranked = sorted(idxs, key=lambda i: len(rows[i].verbatim_snippet or ""), reverse=True)
        keep.update(ranked[:cap])
    return [row for i, row in enumerate(rows) if i in keep]


def cap_rows_per_law(
    rows: list["SubmissionRow"], *, cap: int = 8
) -> list["SubmissionRow"]:
    """Keep at most ``cap`` provisions per LAW, balanced across its indicators.

    The per-(law, indicator) cap still lets one big statute dominate the whole
    economy: the 174 KB Queensland state IP Act produced ~35 rows across four
    indicators, swamping the federal Privacy Act 1988 in the Australia output —
    misleading for a national-level assessment. This caps the total per law and,
    when trimming, keeps a balanced spread across the indicators the law touches
    (round-robin by longest quote) rather than a single indicator's long tail.
    Purely a tidiness pass — it never fabricates or reorders kept rows.
    """
    if cap <= 0:
        return rows
    # Group by the NORMALISED law name so a statute's title variants — a country
    # prefix, an ALL-CAPS copy, a "(PDPA)" acronym — collapse into one law and
    # the cap actually bites (a live MYS run surfaced the PDPA under ~5 variant
    # names, 20 rows, which evaded a raw-name cap).
    from .novelty import normalize_law_name

    by_law: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        law = normalize_law_name(row.law_name or "") or " ".join((row.law_name or "").split()).casefold()
        by_law.setdefault(law, []).append(i)
    keep: set[int] = set()
    for idxs in by_law.values():
        if len(idxs) <= cap:
            keep.update(idxs)
            continue
        # Bucket the law's rows by indicator, each ranked by quote length.
        per_ind: dict[str, list[int]] = {}
        for i in idxs:
            per_ind.setdefault(rows[i].indicator_id, []).append(i)
        for lst in per_ind.values():
            lst.sort(key=lambda i: len(rows[i].verbatim_snippet or ""), reverse=True)
        # Round-robin across indicators until the cap is reached.
        order = sorted(per_ind)
        chosen: list[int] = []
        pos = 0
        while len(chosen) < cap and any(per_ind[k] for k in order):
            bucket = per_ind[order[pos % len(order)]]
            if bucket:
                chosen.append(bucket.pop(0))
            pos += 1
        keep.update(chosen)
    return [row for i, row in enumerate(rows) if i in keep]


def dedupe_submission_rows(rows: list["SubmissionRow"]) -> list["SubmissionRow"]:
    """Drop duplicate provisions (same indicator + same law + same verbatim quote).

    Long statutes run through extraction can surface the identical clause in
    several chunks; shipping the same (indicator, quote) twice inflates the
    submission and reads as padding to judges. Keeps first occurrence, order
    preserved. Rows with an empty quote are never treated as duplicates.
    """
    from .novelty import normalize_law_name

    seen: set[tuple[str, str, str]] = set()
    out: list["SubmissionRow"] = []
    for row in rows:
        quote = " ".join((row.verbatim_snippet or "").split()).casefold()
        law = normalize_law_name(row.law_name or "") or " ".join((row.law_name or "").split()).casefold()
        key = (row.indicator_id, law, quote)
        if quote and key in seen:
            continue
        if quote:
            seen.add(key)
        out.append(row)
    return out


# A verbatim quote at least this long is treated as a substantive provision.
# Below it, the quote must (approximately) be the law's own title to be kept —
# that is the legitimate "framework exists" evidence pattern for indicators like
# P7-I1 (the golden set carries such title-quotes, e.g. "Privacy Act 1988").
# Anything shorter that is NOT the title is a mid-sentence fragment the extractor
# emitted by mistake ("data processor", "personal data") and is dropped.
_MIN_PROVISION_QUOTE_LEN = 45
# An international instrument is not a domestic measure the RDTII scores at the
# national level (the official assessment records e.g. "binding commitments"
# as an assessment note, not by extracting clauses from the FTA). The golden set
# contains no such source. Dropping these clears the trade-agreement over-
# extraction the live-discovery path pulls in (13 of 26 SGP rows in one run).
_OUT_OF_SCOPE_INSTRUMENT = re.compile(
    r"\b(free trade agreement|digital economy agreement|trade agreement|"
    r"partnership agreement|comprehensive and progressive agreement|"
    r"economic partnership|\bfta\b|\bdea\b|\bcptpp\b|\brcep\b|\bdepa\b|"
    r"treaty|convention|protocol)\b",
    re.IGNORECASE,
)
# A blog / news / press page is not authoritative legal text even on an official
# domain (e.g. an IMDA blog article surfaced as a "law"). Matches by URL path.
_NON_AUTHORITATIVE_URL = re.compile(
    r"/(blog|blog-articles|news|newsroom|press|press-releases?|article|articles|"
    r"media-release|speeches?)(/|$)",
    re.IGNORECASE,
)
# A trade-agreement source by URL — the FTA portal or a TPPA/CPTPP/RCEP text —
# catches instrument chapters whose name hides the agreement ("Chapter 14
# Electronic Commerce" served from the FTA portal is a CPTPP chapter).
_AGREEMENT_URL = re.compile(
    r"//fta\.|/miti-fta/|/tppa|/cptpp|/rcep\b|trans-pacific|free-?trade-?agreement",
    re.IGNORECASE,
)
# A foreign jurisdiction named in a domestic-law title is a mislabel: none of
# these are economies the tool runs (a Malaysia PDPA page was tagged "Hong Kong
# Personal Data (Privacy) Ordinance" / "Singapore PDPA" by the extractor). The
# golden set contains no such source.
# Economy-aware jurisdiction markers: a row produced in a run for economy X is
# dropped when its law name carries the marker of a DIFFERENT covered economy
# (e.g. "China Personal Information Protection Law" surfacing in a Singapore
# run via a multi-jurisdiction digest document). Static _FOREIGN_JURISDICTION
# below stays for jurisdictions we never cover; this map handles the covered
# ten, where a blanket blacklist would break their own runs.
_ECONOMY_MARKERS: dict[str, "re.Pattern[str]"] = {
    "SGP": re.compile(r"\bsingapore\b", re.IGNORECASE),
    "MYS": re.compile(r"\bmalaysia|malaysian\b", re.IGNORECASE),
    "AUS": re.compile(r"\baustralia|australian\b", re.IGNORECASE),
    "CHN": re.compile(r"\bchina|chinese|people's republic of china|\bprc\b", re.IGNORECASE),
    "IND": re.compile(r"\bindia\b|\bindian\b", re.IGNORECASE),
    "IDN": re.compile(r"\bindonesia|indonesian\b", re.IGNORECASE),
    "LAO": re.compile(r"\blao\b|\blaos\b", re.IGNORECASE),
    "MNG": re.compile(r"\bmongolia|mongolian\b", re.IGNORECASE),
    "RUS": re.compile(r"\brussia|russian\b", re.IGNORECASE),
    "THA": re.compile(r"\bthailand\b|\bthai\b", re.IGNORECASE),
}


def _is_foreign_law_for_economy(economy: str, law_name: str) -> bool:
    """True when the law name names a DIFFERENT covered economy than the run's.

    Deterministic and conservative: fires only when the name carries another
    covered economy's marker AND does not carry the run economy's own marker
    (so "Australia-Singapore ..." in a Singapore run is left to the instrument
    gate rather than guessed at here)."""
    name = law_name or ""
    if not name:
        return False
    try:
        code = economy_code(economy)
    except Exception:  # noqa: BLE001 — unknown economy: do not guess
        return False
    own = _ECONOMY_MARKERS.get(code)
    if own is not None and own.search(name):
        return False
    return any(
        marker.search(name)
        for other, marker in _ECONOMY_MARKERS.items()
        if other != code
    )


# A bill / draft / consultation / digest is not an in-force statutory measure.
# ("PERSONAL DATA PROTECTION DIGEST" and the India DPDP *Bill* both surfaced as
# "laws" via a multi-jurisdiction compendium document.)
_NON_STATUTE_INSTRUMENT = re.compile(
    r"\b(bill|draft|consultation( paper)?|white paper|green paper|digest|"
    r"handbook|compendium|proposed|at a glance|fact\s?sheet|faq)\b",
    re.IGNORECASE,
)


# The RDTII methodology "excludes pending draft and repealed measures" (internal
# guide p.8). Official portals (legislation.gov.au, SSO, AustLII) mark a repealed
# instrument in its very title — "Foo Act 1990 (Repealed)". We match ONLY that
# explicit parenthetical/bracketed status marker: high precision, so a valid
# statute is never dropped for merely quoting a repeal clause, and a live-in-force
# "Statute Law (Repeals) Act" or "... Repeal Act" is untouched (those say
# "repeals"/"repeal", not the "(repealed)" status).
_REPEALED_LAW_NAME = re.compile(r"[\(\[]\s*repealed\s*[\)\]]", re.IGNORECASE)


# RDTII rule (framework guide, confirmed): "A measure applied to the Government
# data should not be scored, because the indicator focuses on a measure
# potentially affecting commercial transactions" — named explicitly for Pillar 6.
# So a provision that regulates GOVERNMENT records (their destruction, retention,
# access) is not scoreable evidence. We match the government-record OBJECT, and
# guard with a personal/commercial-data check so a personal-data law that merely
# mentions government (e.g. the Identity Verification Services Act's "facial image"
# obligations that reference a Commonwealth record) is NOT dropped.
_GOVERNMENT_DATA_OBJECT = re.compile(
    r"\bcommonwealth record|\bgovernment record|\bpublic record|\bstate records?\b"
    r"|\bofficial records?\s+relating to (?:affairs of )?state"
    r"|\bpublic[- ]sector record",
    re.IGNORECASE,
)
_PERSONAL_DATA_SUBJECT = re.compile(
    r"personal (?:data|information)|facial image|biometric|identification information"
    r"|individual'?s?\s+(?:data|information|image)|data subject",
    re.IGNORECASE,
)


# Pillar 6 is about DATA flows. A P6 row whose quote contains no data-ish
# language at all is usually the extractor mis-reading a licence/asset/permit
# "transfer" provision (Gas Act, aviation Acts...). We FLAG, never drop — the
# call is semantic and belongs to the human reviewer. Verified: all 13 golden
# P6 quotes contain at least one of these terms.
_P6_DATA_TOPIC = re.compile(
    r"(data|information|personal|record|database|server|network|comput|"
    r"electronic|privacy|storage)",
    re.IGNORECASE,
)

_P6_TOPIC_FLAG = (
    "topic check: quote contains no data/information language — possible "
    "non-data 'transfer' (licence/asset/permit); needs human review"
)


def _flag_p6_topic_mismatch(row) -> None:
    """Append a loud human-review note to off-topic-looking P6 rows (in place)."""
    ind = str(getattr(row, "indicator_id", "") or "")
    quote = str(getattr(row, "verbatim_snippet", "") or "")
    if not ind.startswith("P6") or not quote:
        return
    if _P6_DATA_TOPIC.search(quote):
        return
    notes = str(getattr(row, "notes", "") or "")
    if _P6_TOPIC_FLAG in notes:
        return
    row.notes = f"{notes}; {_P6_TOPIC_FLAG}" if notes else _P6_TOPIC_FLAG
    if hasattr(row, "requires_human_review"):
        row.requires_human_review = True


# Indicator 7.3 scores 1 ONLY when a law mandates a SPECIFIC MINIMUM retention
# period (RDTII methodology + the grader on our own assignment: "7.3 focuses on
# the duration of keeping data… no minimum period = 0"). A 7.3 evidence row whose
# quote states no explicit minimum period (a data-minimisation "destroy" /
# "cease to retain" rule, a response deadline, or a portability-timing clause)
# scores 0 and is weak 7.3 evidence. FLAG for the human reviewer — never drop
# (it may still be legitimate context, and the reviewer makes the call).
_MIN_RETENTION_PERIOD = re.compile(
    r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty)\s*"
    r"(?:year|month|day|week)s?\b"
    r"|\bnot less than\b|\bno less than\b|\bat least\b"
    r"|\bminimum (?:period|retention)\b"
    r"|不少于|不得低于|至少",
    re.IGNORECASE,
)
_P7_I3_NO_PERIOD_FLAG = (
    "retention check: quote states no specific minimum retention period — "
    "scores 0 for 7.3 per the methodology (7.3 = duration of keeping data); "
    "needs human review"
)


def _flag_7_3_no_minimum_period(row) -> None:
    """Flag a 7.3 row whose quote states no specific minimum retention period."""
    if str(getattr(row, "indicator_id", "") or "") != "P7-I3":
        return
    quote = str(getattr(row, "verbatim_snippet", "") or "")
    if not quote or _MIN_RETENTION_PERIOD.search(quote):
        return
    notes = str(getattr(row, "notes", "") or "")
    if _P7_I3_NO_PERIOD_FLAG in notes:
        return
    row.notes = f"{notes}; {_P7_I3_NO_PERIOD_FLAG}" if notes else _P7_I3_NO_PERIOD_FLAG
    if hasattr(row, "requires_human_review"):
        row.requires_human_review = True


# 6.1/6.2/6.3 are the data-LOCALIZATION indicators (ban / local storage /
# infrastructure). A genuine row asserts a restriction on cross-border transfer
# OR a local-storage/processing/infrastructure requirement. The live path
# sometimes maps a PERMISSIVE disclosure/sharing provision onto them (e.g.
# Singapore's Financial Services and Markets Act inter-institution information
# sharing "may disclose to…" read as 6.1). A 6.1/6.2/6.3 quote with none of the
# restriction/localization signals below is such a mis-map — FLAG for human
# review (never drop; the reviewer confirms).
_P6_RESTRICTION_LANGUAGE = re.compile(
    r"shall not transfer|must not transfer|may not transfer|not be transferred"
    r"|prohibit|restrict|\bban\b|localiz"
    r"|local (?:storage|processing)|stored?\s+(?:in|within|locally)"
    r"|kept\s+(?:in|within|by|at)|held?\s+(?:in|within)"
    r"|within (?:the )?(?:country|territory|singapore|malaysia|australia|jurisdiction)"
    r"|data\s+cent|server\s+(?:located|s?\s+in)|\breside|onshore"
    r"|not\s+(?:be\s+)?(?:transfer|disclos|sen[dt]|hold|take|remov)\w*\s+(?:to|outside|out of)"
    r"|(?:transfer|disclos)\w*[^.]{0,50}\b(?:only if|unless|where the|subject to)\b"
    r"|outside\s+(?:the\s+)?(?:country|singapore|malaysia|australia)"
    r"|不得(?:传输|转移|向境外)|本地(?:存储|处理)|境内",
    re.IGNORECASE,
)
_P6_LOC_NO_RESTRICTION_FLAG = (
    "topic check: 6.1/6.2/6.3 is a data-localization indicator but the quote "
    "states no transfer-restriction / local-storage / infrastructure requirement "
    "(may be a permissive disclosure/sharing provision) — needs human review"
)


def _flag_p6_localization_missing(row) -> None:
    """Flag a 6.1/6.2/6.3 row whose quote asserts no localization/restriction."""
    if str(getattr(row, "indicator_id", "") or "") not in _P6_LOCALIZATION_INDICATORS:
        return
    quote = str(getattr(row, "verbatim_snippet", "") or "")
    if not quote or _P6_RESTRICTION_LANGUAGE.search(quote):
        return
    notes = str(getattr(row, "notes", "") or "")
    if _P6_LOC_NO_RESTRICTION_FLAG in notes:
        return
    row.notes = f"{notes}; {_P6_LOC_NO_RESTRICTION_FLAG}" if notes else _P6_LOC_NO_RESTRICTION_FLAG
    if hasattr(row, "requires_human_review"):
        row.requires_human_review = True


# A law whose NAME is squarely a non-digital, goods/agriculture/charges domain
# cannot be P6/P7 (cross-border data / data protection) evidence. The live path
# occasionally maps such a law onto a P6/P7 indicator ("Wine Export Charge Act"
# -> 7.5). These terms never appear in a genuine data/privacy statute name, so a
# P6/P7 row named for one is dropped. (Terms like tariff/levy/excise are left out
# — those belong to Pillar 1 and would be legitimate there.)
_OFF_TOPIC_DOMAIN = re.compile(
    r"\b(wine|dairy|livestock|fisher\w*|agricultur\w*|horticultur\w*|wool|"
    r"poultry|forestry|primary\s+industr\w*|export\s+charge|customs\s+charge|"
    r"grain|sugar|meat|seafood|viticultur\w*|"
    # Export-control-of-goods regimes (strategic/dual-use/military goods) are a
    # trade-in-goods domain, NOT cross-border DATA (P6) or data protection (P7).
    # The live path mapped Singapore's "Strategic Goods (Control) Act" onto 6.1
    # ("'goods' means any movable property" read as data localization).
    r"strategic\s+goods|export\s+control|dual[- ]use|munitions?|"
    r"firearms?|weapons?|arms\s+(?:control|trade|export)|military\s+end)\b",
    re.IGNORECASE,
)

# Evidence quoted from an un-enacted DRAFT bill is not an in-force measure. The
# live path sometimes hangs a draft-bill quote on an in-force law's name (e.g. a
# "Draft Bill" cyber-notification clause labelled as the enacted PDPA). We catch
# the draft-bill tell in the VERBATIM (the law-name gate already catches names
# containing "bill"/"draft"); a genuine in-force provision says "this Act", never
# "the Draft Bill".
_DRAFT_EVIDENCE = re.compile(r"\bdraft bill\b|\bexposure draft\b", re.IGNORECASE)


def _is_draft_evidence(quote: str) -> bool:
    return bool(_DRAFT_EVIDENCE.search(quote or ""))


# A payment / e-money statute mapped to a data-LOCALIZATION indicator (6.1-6.3)
# is off-topic UNLESS the quote actually states a data-location requirement.
# Payment-data localization is real in some economies, so we do NOT drop on the
# law name alone — only when the quote carries no locality language at all (the
# live path mapped Singapore's Payment Services Act e-money account rules onto
# 6.1).
_PAYMENT_LAW = re.compile(r"\bpayment\s+services?\b|\be-?money\b|\bpayment\s+systems?\b", re.IGNORECASE)
_LOCALIZATION_LANGUAGE = re.compile(
    r"localiz\w*|local\s+(?:storage|processing|copy)|stored?\s+(?:in|within|locally)|"
    r"within\s+(?:the\s+)?(?:country|territory|singapore|malaysia|australia|jurisdiction)|"
    r"data\s+cent|server\s+(?:located|s?\s+in)|reside\w*\s+(?:in|within)|"
    r"kept\s+(?:in|within)|physically\s+(?:in|located|stored)|onshore|cross[- ]border\s+transfer",
    re.IGNORECASE,
)
_P6_LOCALIZATION_INDICATORS = frozenset({"P6-I1", "P6-I2", "P6-I3"})


def _is_payment_law_off_localization(law_name: str, quote: str, indicator_id: str) -> bool:
    if (indicator_id or "").upper() not in _P6_LOCALIZATION_INDICATORS:
        return False
    if not _PAYMENT_LAW.search(law_name or ""):
        return False
    return not _LOCALIZATION_LANGUAGE.search(quote or "")


# Rationale/law-name subject mismatch: a genuine rationale opens "[<ref>] Section
# X of <the row's own law> …". The confabulated live rows open "[<ref>] Section X
# of <a DIFFERENT statute>" — the model narrated a different law than the row is
# labelled with (e.g. law_name "Identity Verification Services Act" but rationale
# "Section 9 of Australia's Privacy Act 1988"). We extract the SUBJECT statute
# named at the start of the rationale and drop when its core token set is
# disjoint from the law-name's. High precision: a mere cross-reference later in
# the rationale (My Health Records s5 "…also an authorisation for the purposes of
# the Privacy Act 1988") is NOT the subject and does not trip it.
_RATIONALE_SUBJECT = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*)?(?:the\s+(?:scope|measure|provision|analysis)[^.]*?\bunder\b\s+|"
    r"(?:section|clause|regulation|paragraph|article|part)\s+[\w().-]+\s+of\s+)"
    r"(?:the\s+)?(?:australia'?s?|singapore'?s?|malaysia'?s?|australian\s+)?\s*"
    r"([A-Z][A-Za-z'()&/ ]+?(?:Act|Regulations?|Ordinance|Decree|Principles?|Instruction|Agreement))\b",
    re.IGNORECASE,
)
_STOPWORDS = frozenset({"the", "of", "and", "act", "regulations", "regulation", "an",
                        "australia", "australian", "singapore", "malaysia", "s"})


def _core_tokens(name: str) -> set:
    toks = re.findall(r"[a-z0-9]+", (name or "").lower())
    return {t for t in toks if t not in _STOPWORDS and len(t) > 2}


def _rationale_names_other_statute(law_name: str, rationale: str) -> bool:
    m = _RATIONALE_SUBJECT.match(rationale or "")
    if not m:
        return False
    subj = _core_tokens(m.group(1))
    name = _core_tokens(law_name)
    if not subj or not name:
        return False
    # Mismatch only when the rationale-subject shares NO substantive token with
    # the row's law name (disjoint) — so "IVS Act" vs "Privacy Act" trips, but
    # "My Health Records Act" vs "My Health Records Act 2012" does not.
    return subj.isdisjoint(name)


def _is_off_topic_law(law_name: str, indicator_id: str = "") -> bool:
    """A goods/agriculture-domain law mapped to P6/P7 is out of scope."""
    ind = (indicator_id or "").upper()
    if not (ind.startswith("P6") or ind.startswith("P7") or ind.startswith(("6.", "7."))):
        return False
    return bool(_OFF_TOPIC_DOMAIN.search(law_name or ""))


# When one source URL is claimed by THREE OR MORE distinct law names in a single
# run, that is the tell-tale of a fabricated discovery — the model invented names
# and hung them on whatever URL it had (e.g. five "laws" all pointing at the one
# IVS Act 2023 register page). We FLAG every such row (never drop — one of the
# names is the real law at that URL) so the reviewer and score_vs_official can
# see it. Threshold 3: two names on one URL (an Act + its amendment) is normal.
_URL_REUSE_THRESHOLD = 3
_URL_REUSE_FLAG = (
    "hallucination check: this source URL is claimed by 3+ different law names "
    "in this run — likely a fabricated name on a real URL; verify at the source"
)


def _is_non_statute_instrument(law_name: str) -> bool:
    return bool(_NON_STATUTE_INSTRUMENT.search(law_name or ""))


def _is_repealed_law(law_name: str) -> bool:
    """True when the law's title carries the explicit "(Repealed)" status marker."""
    return bool(_REPEALED_LAW_NAME.search(law_name or ""))


# The government-data exclusion is NOT a blanket rule. The methodology states it
# only for the data-localization indicators 6.1-6.4 ("Not score data localization
# measure applied to government data") and the retention indicator 7.3 ("Not score
# requirement applied to government data"). It does NOT apply to 7.1/7.2/7.4/7.5.
_GOV_DATA_EXCLUDED_INDICATORS: frozenset[str] = frozenset(
    {"P6-I1", "P6-I2", "P6-I3", "P6-I4", "P7-I3"}
)


def _is_government_data_measure(law_name: str, quote: str) -> bool:
    """True when a provision regulates GOVERNMENT records (not scoreable per the
    methodology), and is not really about personal/commercial data."""
    blob = f"{law_name or ''} {quote or ''}"
    return bool(_GOVERNMENT_DATA_OBJECT.search(blob)) and not _PERSONAL_DATA_SUBJECT.search(blob)


# The verbatim must be the OPERATIVE provision text, not the law's name or a bare
# section heading. The LLM sometimes returns "Cyber Security Act 2024: Section 3
# Objects" or just "Credit Reporting Agencies Act 2010 (Act 710)" as the quote —
# judges paste the verbatim next to the source and such a row reads as garbage.
_OPERATIVE_LANGUAGE = re.compile(
    r"\b(shall|must|may|required?|prohibit|prohibited|liable|entitled|obliged|"
    r"obligation|no person|any person|an? organisation|means|includes?|access|"
    r"disclose|retain|store|transfer|process|collect|appoint|designate|ensure|"
    r"comply|provide|impose|permit|restrict)\b"
    r"|应当|不得|必须|禁止|ต้อง|ห้าม|обязан|запрещ"
    # Malay/Indonesian operative verbs (Malay statutes: 'hendaklah melantik…')
    r"|wajib|dilarang|hendaklah|mestilah|tidak boleh|melantik",
    re.IGNORECASE,
)


def _norm_alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# A verbatim that is only a citation + a parenthesised marginal heading, e.g.
# "Criminal Procedure Code 2010 — Section 39 (Power to access computer)". These
# slip the operative-language check because the heading itself contains an
# operative word ("access"), yet there is no operative sentence — the quote ends
# right after the bracketed heading. A real provision continues past it (a
# subsection number like "(1)" is <3 chars and never matches).
_CITATION_HEADING_ONLY = re.compile(
    r"^.{0,70}?[—–:-]\s*"
    r"(?:section|s\.?|art\.?|article|reg(?:ulation)?\.?|para(?:graph)?\.?|clause)\s*"
    r"[\w().]+\s*\([^)]{3,70}\)\s*$",
    re.IGNORECASE,
)


def _is_nonsubstantive_quote(law_name: str, quote: str) -> bool:
    """True when the verbatim is the law's NAME / a section heading rather than an
    operative clause (no operative or definitional language). High precision: a
    real provision that merely opens with the statute name but then states an
    obligation is kept (it contains operative language)."""
    q = (quote or "").strip()
    if len(q) < 15:
        return True
    # A bare "<Law> — Section N (Heading)" citation is a heading, not a provision,
    # even when the heading text contains an operative word.
    if _CITATION_HEADING_ONLY.match(q):
        return True
    base = _norm_alnum(re.split(r"[—–:(]", law_name or "")[0])
    starts_with_name = len(base) >= 12 and _norm_alnum(q).startswith(base[:22])
    return starts_with_name and not _OPERATIVE_LANGUAGE.search(q)


# A law name must contain SOME statutory-instrument word (multi-language). The
# live path occasionally names a row after a document that is not legislation
# at all ("Executive Summary", "MOU with ...", "RDTII 2.1 ... assessment").
# Empirically validated against all law names across three economies' judge
# runs + the full library + the golden set: exactly the garbage drops, all 46
# legitimate names keep (Acts, Regulations, Decrees, Notices, Principles...).
# Round-2 re-validation against the official inventory (2026-08-01) added
# decision/resolution/instruction: LAO ministries legislate via "Decision
# No. X/MPT" (12+ inventory instruments), MNG/RUS via "Resolution of the
# Government No. X" (the Russian original постановление was covered but its
# English translation was not), IDN/LAO via "Instruction No. X". No historical
# garbage name ("Executive Summary", "MOU...", "Annual Report", FIR) contains
# any of the three.
# 2026-08-01 2nd pass: scan_gate_misses.py revealed 125/684 official inventory
# names would be dropped. The biggest gaps: CHN 公告(announcement)/目录(catalogue)/
# 方案(plan)/规范(specification)/措施(measures)/通知(notification), IND
# Notification/Circular/Direction/Policy/Guideline/Framework/Procedure. Words
# below are intentionally the conservative subset that unblocks real legislation
# while still dropping Annual Report/Court/Writ Petition/Press Release/Website/
# Consultation Paper/FIR — none of which contain any added term.
_STATUTE_INSTRUMENT_WORD = re.compile(
    r"(act|law|regulation|code|ordinance|decree|rule|order|constitution|"
    r"notice|notification|announcement|principle|bill|standard|amendment|schedule|"
    r"decision|resolution|instruction|"
    r"circular|measures|catalogue|specification|plan|policy|procedure|"
    r"guideline|guidelines|direction|directive|framework|"
    # Malay statutory-instrument words (Akta 709, Peraturan-Peraturan,
    # Pekeliling = official circular, Perintah = order)
    r"akta|peraturan|pekeliling|perintah|kanun|undang-undang|"
    # Thai / Russian / Mongolian
    r"กฎหมาย|พระราช|ประกาศ|закон|кодекс|указ|постановление|хууль|"
    # Chinese: 法(law) 条例(regulations) 办法(measures) 规定(provisions)
    # 公告(announcement) 目录(catalogue) 方案(plan) 规范(specification)
    # 通知(notification/circular) 计划(plan) 预案(emergency plan) 措施(measures)
    r"法|条例|办法|规定|公告|目录|方案|规范|通知|计划|预案|措施)",
    re.IGNORECASE,
)


def _lacks_statute_word(law_name: str) -> bool:
    name = (law_name or "").strip()
    return bool(name) and not _STATUTE_INSTRUMENT_WORD.search(name)


_FOREIGN_JURISDICTION = re.compile(
    r"\b(hong\s*kong|viet\s*nam|vietnam|south\s*korea|korea|japan|"
    r"european\s+union|united\s+kingdom|united\s+states|new\s+zealand)\b",
    re.IGNORECASE,
)


def _is_out_of_scope_source(law_name: str, source_url: str) -> bool:
    """True if the row's source is not a domestic statutory measure.

    Filters (a) international instruments (FTAs, digital-economy agreements —
    not national measures) and (b) non-authoritative pages (blog/news/press),
    both of which the live-discovery path over-extracts. Verified against the
    golden set: neither pattern hits any approved case.
    """

    if _OUT_OF_SCOPE_INSTRUMENT.search(law_name or ""):
        return True
    if _FOREIGN_JURISDICTION.search(law_name or ""):
        return True
    if _NON_AUTHORITATIVE_URL.search(source_url or ""):
        return True
    if _AGREEMENT_URL.search(source_url or ""):
        return True
    return False
_STATUTE_WORD = re.compile(
    r"\b(act|law|regulation|regulations|ordinance|decree|code|rules|bill|"
    r"constitution|notification|akta|peraturan|pekeliling|perintah)\b",
    re.IGNORECASE,
)


def _quote_key(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


# A short quote that is just the law's title is legitimate evidence ONLY for the
# comprehensive-framework indicator (P7-I1): "this data-protection law exists".
# The golden set carries such title-quotes for P7-I1 and no other indicator, so
# a title-quote mapped to a provision-specific indicator (retention, DPO,
# government access, cross-border) is weak evidence and is dropped.
_FRAMEWORK_INDICATOR = "P7-I1"


def _is_weak_evidence(law_name: str, quote: str, indicator_id: str = "") -> bool:
    """True if the quote is too weak to stand as evidence for the row.

    Rejects (a) short mid-sentence fragments that are neither a provision nor the
    law's title ("data processor", "personal data"), and (b) a bare title-quote
    ("Privacy Act 1988") mapped to any indicator other than the comprehensive-
    framework one — the only indicator for which a law's mere existence is the
    accepted evidence (per the golden set). A substantive provision quote is
    always kept.
    """

    q = (quote or "").strip()
    if len(q) >= _MIN_PROVISION_QUOTE_LEN:
        return False
    nq, nl = _quote_key(q), _quote_key(law_name)
    qt, lt = set(nq.split()), set(nl.split())
    # A title-quote carries a statute-type word and its tokens are a subset of
    # (or superset of) the law-name tokens — robust to a country prefix or a
    # "(PDPA)" acronym sitting between the name and the year.
    looks_like_title = bool(_STATUTE_WORD.search(q)) and bool(qt) and bool(lt) and (
        qt <= lt or lt <= qt
    )
    if not looks_like_title:
        return True  # short mid-sentence fragment
    # A title-quote is valid evidence only for the framework indicator.
    return (indicator_id or "").strip().upper() != _FRAMEWORK_INDICATOR


# Backwards-compatible alias (indicator-agnostic fragment check).
def _is_fragment_quote(law_name: str, quote: str) -> bool:
    return _is_weak_evidence(law_name, quote, _FRAMEWORK_INDICATOR)


def _canonical_name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.split(r"[—–]", name or "")[0].lower())


def canonicalize_law_names_per_url(rows: list[SubmissionRow]) -> list[SubmissionRow]:
    """Collapse the many law names the extractor can attach to ONE source URL.

    A single document (URL) is a single law, but the LLM fills source_legislation
    from what a quote *talks about* — so a provision inside the IVS Act that
    references the Privacy Act gets mislabelled "Privacy Act 1988". That is the
    one-URL-many-names hallucination. Force every row sharing a URL to one
    canonical name: an authoritative library/seed name if any row on that URL has
    one (cached_discovery / known_mapping), else the most common name (tie-broken
    by the longest name carrying a statutory-instrument word). Renamed rows get a
    note; the downstream dedupe then merges the true duplicates. Runs before
    dedupe, at the final submission boundary.
    """
    from collections import Counter, defaultdict

    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        url = str(getattr(r, "source_url", "") or "").strip()
        if url:
            groups[url].append(r)

    for url, group in groups.items():
        names = [str(getattr(r, "law_name", "") or "").strip() for r in group]
        names = [n for n in names if n]
        if len({_canonical_name_key(n) for n in names}) < 2:
            continue  # already consistent — nothing to collapse
        seed = [
            str(getattr(r, "law_name", "") or "").strip()
            for r in group
            if str(getattr(r, "retrieval_method", "") or "") in ("cached_discovery", "known_mapping")
            and getattr(r, "law_name", "")
        ]
        if seed:
            canonical = Counter(seed).most_common(1)[0][0]
        else:
            counts = Counter(names)
            best = counts.most_common(1)[0][1]
            tied = [n for n, c in counts.items() if c == best]
            canonical = max(tied, key=lambda n: (bool(_STATUTE_INSTRUMENT_WORD.search(n)), len(n)))
        for r in group:
            if _canonical_name_key(str(getattr(r, "law_name", "") or "")) != _canonical_name_key(canonical):
                note = str(getattr(r, "notes", "") or "")
                add = f"law name normalised to the source document: {canonical}"
                r.notes = f"{note}; {add}" if note else add
                r.law_name = canonical
                r.law_number_ref = extract_law_number_ref(canonical, getattr(r, "law_number_ref", "") or "")
    return rows


def validate_submission_rows(
    rows: list[SubmissionRow],
    *,
    allow_empty: bool = False,
) -> list[SubmissionRow]:
    """Return the judge-usable rows, dropping incomplete ones with a warning.

    A row missing a judge-critical field (source, quote, law, indicator) is
    dropped rather than allowed to suppress the whole submission — a single
    bad row must never leave a judge with zero output files. Rows whose verbatim
    quote is a short mid-sentence fragment (not a provision and not the law
    title) are also dropped: they are extractor noise, not evidence. Raises only
    when NO usable row remains (unless ``allow_empty``).
    """
    import logging

    logger = logging.getLogger(__name__)

    # Pre-count distinct law names per source URL, for the hallucination flag.
    # Normalise names to alphanumerics only, so the same law named with an
    # invisible variant (nbsp, a stray dash) across its own provisions is NOT
    # miscounted as several laws — only genuinely different names trip the flag.
    _names_per_url: dict[str, set] = {}
    for r in rows:
        url = str(getattr(r, "source_url", "") or "").strip()
        # base act name only (drop a "— s.12A" section suffix) — several provisions
        # of one act on one URL are legitimate, only different acts trip the flag.
        base = re.split(r"[—–]", str(getattr(r, "law_name", "") or ""))[0]
        name = re.sub(r"[^a-z0-9]", "", base.lower())
        if url and name:
            _names_per_url.setdefault(url, set()).add(name)

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
        if _is_weak_evidence(
            str(getattr(row, "law_name", "") or ""),
            str(getattr(row, "verbatim_snippet", "") or ""),
            str(getattr(row, "indicator_id", "") or ""),
        ):
            logger.warning(
                "Dropping submission row %d: weak evidence — quote is a fragment, "
                "or a title-quote on a non-framework indicator (%s: %r)",
                index, getattr(row, "indicator_id", ""),
                str(getattr(row, "verbatim_snippet", ""))[:40],
            )
            continue
        if _is_out_of_scope_source(
            str(getattr(row, "law_name", "") or ""),
            str(getattr(row, "source_url", "") or ""),
        ):
            logger.warning(
                "Dropping submission row %d: out-of-scope source (international "
                "instrument or non-authoritative page): %r",
                index, str(getattr(row, "law_name", ""))[:50],
            )
            continue
        if _is_foreign_law_for_economy(
            str(getattr(row, "economy", "") or ""),
            str(getattr(row, "law_name", "") or ""),
        ):
            logger.warning(
                "Dropping submission row %d: names a different jurisdiction than "
                "the run economy (%s): %r — likely extracted from a "
                "multi-jurisdiction document",
                index, getattr(row, "economy", ""),
                str(getattr(row, "law_name", ""))[:50],
            )
            continue
        if _is_non_statute_instrument(str(getattr(row, "law_name", "") or "")):
            logger.warning(
                "Dropping submission row %d: not an in-force statutory measure "
                "(bill/draft/consultation/digest): %r",
                index, str(getattr(row, "law_name", ""))[:50],
            )
            continue
        if _is_repealed_law(str(getattr(row, "law_name", "") or "")):
            logger.warning(
                "Dropping submission row %d: law is marked repealed — the "
                "methodology excludes repealed measures: %r",
                index, str(getattr(row, "law_name", ""))[:50],
            )
            continue
        if str(getattr(row, "indicator_id", "") or "") in _GOV_DATA_EXCLUDED_INDICATORS and _is_government_data_measure(
            str(getattr(row, "law_name", "") or ""),
            str(getattr(row, "verbatim_snippet", "") or ""),
        ):
            logger.warning(
                "Dropping submission row %d: measure regulates government records, "
                "not commercial data — the methodology does not score government "
                "data for this indicator: %r",
                index, str(getattr(row, "law_name", ""))[:50],
            )
            continue
        if _is_nonsubstantive_quote(
            str(getattr(row, "law_name", "") or ""),
            str(getattr(row, "verbatim_snippet", "") or ""),
        ):
            logger.warning(
                "Dropping submission row %d: verbatim is the law name / a section "
                "heading, not an operative provision: %r",
                index, str(getattr(row, "verbatim_snippet", ""))[:60],
            )
            continue
        if str(getattr(row, "indicator_id", "") or "") in NON_REGULATORY_INDICATORS:
            logger.warning(
                "Dropping submission row %d: indicator %s is NON-REGULATORY "
                "(derived from external databases / treaty-membership checks, not "
                "from a law) — a law-derived evidence row does not belong here: %r",
                index, str(getattr(row, "indicator_id", "")),
                str(getattr(row, "law_name", ""))[:50],
            )
            continue
        if _lacks_statute_word(str(getattr(row, "law_name", "") or "")):
            logger.warning(
                "Dropping submission row %d: name contains no statutory-instrument "
                "word (summary/MOU/report, not legislation): %r",
                index, str(getattr(row, "law_name", ""))[:50],
            )
            continue
        if _is_off_topic_law(
            str(getattr(row, "law_name", "") or ""),
            str(getattr(row, "indicator_id", "") or ""),
        ):
            logger.warning(
                "Dropping submission row %d: goods/agriculture/export-control-domain "
                "law mapped to P6/P7 (out of scope): %r",
                index, str(getattr(row, "law_name", ""))[:50],
            )
            continue
        if _is_draft_evidence(str(getattr(row, "verbatim_snippet", "") or "")):
            logger.warning(
                "Dropping submission row %d: verbatim quotes an un-enacted DRAFT "
                "bill, not an in-force measure: %r",
                index, str(getattr(row, "law_name", ""))[:50],
            )
            continue
        if _is_payment_law_off_localization(
            str(getattr(row, "law_name", "") or ""),
            str(getattr(row, "verbatim_snippet", "") or ""),
            str(getattr(row, "indicator_id", "") or ""),
        ):
            logger.warning(
                "Dropping submission row %d: payment/e-money law mapped to a data-"
                "localization indicator but the quote states no locality "
                "requirement: %r",
                index, str(getattr(row, "law_name", ""))[:50],
            )
            continue
        if _rationale_names_other_statute(
            str(getattr(row, "law_name", "") or ""),
            str(getattr(row, "mapping_rationale", "") or ""),
        ):
            logger.warning(
                "Dropping submission row %d: rationale's subject statute differs "
                "from the row's law name (confabulated mapping): %r",
                index, str(getattr(row, "law_name", ""))[:50],
            )
            continue
        _flag_p6_topic_mismatch(row)
        _flag_p6_localization_missing(row)
        _flag_7_3_no_minimum_period(row)
        # Hallucination flag: 3+ distinct law names on one URL (never drop — one
        # of them is the real law at that URL; surface it for review).
        _url = str(getattr(row, "source_url", "") or "").strip()
        if len(_names_per_url.get(_url, ())) >= _URL_REUSE_THRESHOLD:
            _notes = str(getattr(row, "notes", "") or "")
            if _URL_REUSE_FLAG not in _notes:
                row.notes = f"{_notes}; {_URL_REUSE_FLAG}" if _notes else _URL_REUSE_FLAG
            if hasattr(row, "requires_human_review"):
                row.requires_human_review = True
        valid.append(row)

    if not valid and not allow_empty:
        raise ValueError(
            "No judge-usable provisions were produced (all rows were empty or "
            "incomplete). No output files were written. Check the provider/API "
            "key and network, try --pdf, or use --allow-empty for research runs."
        )
    return valid


def drop_zero_confidence_rows(rows: list[SubmissionRow]) -> list[SubmissionRow]:
    """Drop rows the extractor itself scored at 0.00 confidence.

    Applied at final submission assembly — deliberately NOT inside
    ``validate_submission_rows`` (whose unit fixtures leave ``confidence`` at its
    0.0 default). At assembly time every row has been through real extraction, so
    a 0.00 confidence is a genuine signal: the model had no basis for the mapping.
    Live discovery surfaces marginal instruments — guidance notes ("entities
    should be mindful…"), circular definitions ("has the meaning given under the
    Privacy Act"), administrative instructions, contract clauses — that the
    extractor honestly scores 0.00. These are un-scoreable noise, not evidence.
    Seed / offline runs already carry no 0.00 rows, so this is a no-op there.
    """
    import logging

    logger = logging.getLogger(__name__)
    kept: list[SubmissionRow] = []
    for row in rows:
        try:
            conf = float(getattr(row, "confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        if conf <= 0.0:
            logger.warning(
                "Dropping submission row: zero extractor confidence — not usable "
                "evidence: %r [%s]",
                str(getattr(row, "law_name", ""))[:50],
                str(getattr(row, "indicator_id", "")),
            )
            continue
        kept.append(row)
    return kept


def filter_formal_submission_rows(
    rows: list[SubmissionRow],
    *,
    include_review: bool = False,
    minimum_mapping_confidence: float = 0.8,
) -> list[SubmissionRow]:
    """Keep only precision-first, formally submittable mappings by default.

    Research/review runs may explicitly retain ambiguous rows.  The frozen CSV
    contract is unchanged; this filter only controls which rows reach it.
    """
    if include_review:
        return rows

    import logging

    logger = logging.getLogger(__name__)

    # Flag-not-drop (the RDTII_ELIGIBILITY_MODE=flag default): review-flagged
    # rows STAY in the formal output, annotated for the official 20%
    # human-validation step, instead of being silently excluded — otherwise the
    # orchestrator's flag mode would be undone here at the output boundary.
    # RDTII_ELIGIBILITY_MODE=reject restores the precision-first exclusion.
    if os.getenv("RDTII_ELIGIBILITY_MODE", "flag").strip().lower() != "reject":
        flagged = sum(
            1 for row in rows
            if row.requires_human_review or row.mapping_decision != "supported"
        )
        if flagged:
            logger.info(
                "Keeping %d review-flagged row(s) in the formal output "
                "(flag mode); they carry their reasons in Notes for human "
                "validation.",
                flagged,
            )
        return rows
    kept: list[SubmissionRow] = []
    for row in rows:
        reasons: list[str] = []
        if row.mapping_decision != "supported":
            reasons.append(f"mapping decision is {row.mapping_decision}")
        if row.requires_human_review:
            reasons.append("mapping requires human review")
        if float(row.confidence or 0.0) < minimum_mapping_confidence:
            reasons.append(
                f"mapping confidence {float(row.confidence or 0.0):.2f} < "
                f"{minimum_mapping_confidence:.2f}"
            )
        if reasons:
            logger.warning(
                "Excluding row from formal submission (%s): %r [%s]",
                "; ".join(reasons), row.law_name[:50], row.indicator_id,
            )
            continue
        kept.append(row)
    return kept
