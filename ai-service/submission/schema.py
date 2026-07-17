"""The judge-validated 13-field submission contract.

Column order is frozen: judges validate programmatically and reject renamed or
reordered columns. Do not change ``CSV_COLUMNS`` without confirming against the
official README template.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

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


# A law whose NAME is squarely a non-digital, goods/agriculture/charges domain
# cannot be P6/P7 (cross-border data / data protection) evidence. The live path
# occasionally maps such a law onto a P6/P7 indicator ("Wine Export Charge Act"
# -> 7.5). These terms never appear in a genuine data/privacy statute name, so a
# P6/P7 row named for one is dropped. (Terms like tariff/levy/excise are left out
# — those belong to Pillar 1 and would be legitimate there.)
_OFF_TOPIC_DOMAIN = re.compile(
    r"\b(wine|dairy|livestock|fisher\w*|agricultur\w*|horticultur\w*|wool|"
    r"poultry|forestry|primary\s+industr\w*|export\s+charge|customs\s+charge|"
    r"grain|sugar|meat|seafood|viticultur\w*)\b",
    re.IGNORECASE,
)


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


# A law name must contain SOME statutory-instrument word (multi-language). The
# live path occasionally names a row after a document that is not legislation
# at all ("Executive Summary", "MOU with ...", "RDTII 2.1 ... assessment").
# Empirically validated against all law names across three economies' judge
# runs + the full library + the golden set: exactly the garbage drops, all 46
# legitimate names keep (Acts, Regulations, Decrees, Notices, Principles...).
_STATUTE_INSTRUMENT_WORD = re.compile(
    r"(act|law|regulation|code|ordinance|decree|rule|order|constitution|"
    r"notice|principle|bill|standard|amendment|schedule|"
    r"กฎหมาย|พระราช|ประกาศ|закон|кодекс|указ|постановление|хууль|法|条例|办法|规定)",
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
    r"constitution|notification)\b",
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
                "Dropping submission row %d: goods/agriculture-domain law mapped to "
                "P6/P7 (out of scope): %r",
                index, str(getattr(row, "law_name", ""))[:50],
            )
            continue
        _flag_p6_topic_mismatch(row)
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
