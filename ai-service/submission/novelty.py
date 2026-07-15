"""NEW-law discovery — reconcile the NEW/KNOWN tag against the KNOWN baseline.

The hackathon rewards independently discovering laws that are *not* in the
provided sample kit (``discovery_tag = NEW``). Trusting a discovery adapter's own
method label is weak evidence: the honest test of novelty is whether the law is
absent from our curated **KNOWN** baseline — the local law library
(``data/law_library``).

This module answers, per mapped provision: *is this law already in the KNOWN
baseline?* If yes it is KNOWN; if no it is a genuine NEW find. It then produces a
**discovery report** — a human-review gate that lists NEW candidates with the
audit trail (source URL, verbatim quote, indicator, score) so a lawyer can verify
each one before it is relied on.

Following the "draft for review" guardrail pattern: a NEW find is a lead for
attorney verification, not a settled legal conclusion.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from law_library import LawEntry, load_library

from .schema import SubmissionRow, economy_code

# ai-service/submission/novelty.py -> parents[2] == repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
# The authoritative KNOWN set: the official ESCAP RDTII Legal Inventory for the
# mandatory economies, distilled to (economy, law) keys. A provision whose law is
# in this inventory (or in our curated library) is KNOWN; anything else the tool
# finds in force is a genuine NEW discovery.
KNOWN_INVENTORY_PATH = _REPO_ROOT / "data" / "known_inventory.jsonl"
GOLDEN_CASES_PATH = _REPO_ROOT / "evaluation" / "golden" / "cases.jsonl"
GOLDEN_DOCUMENTS_PATH = _REPO_ROOT / "evaluation" / "golden" / "documents.jsonl"

_PAREN = re.compile(r"\(.*?\)")
_YEAR = re.compile(r"\b\d{4}\b")
# Standalone statute-number tokens the LLM appends verbosely: "No. 709",
# "Act 709", "Cap. 486", "Chapter 14". Parenthesised forms ("(Act 777)") are
# already dropped by _PAREN; this catches the bare forms so "... Act, No. 709"
# reconciles to the same identity as the curated "Personal Data Protection Act".
_ACT_NUMBER = re.compile(r"\b(?:no|act|cap|chapter)\.?\s*[a-z]?\d+\b", re.IGNORECASE)
# A leading economy / nationality prefix the LLM prepends ("Malaysia Personal
# Data Protection Act", "Singapore PDPA"). Identity keys are already scoped by
# (economy, name), so a leading country word is redundant noise that must not
# defeat KNOWN-baseline reconciliation of an economy's own flagship statute.
_LEADING_GEO = re.compile(
    r"^(?:the\s+)?(?:singapore|malaysia|malaysian|australia|australian|china|chinese|"
    r"thailand|thai|india|indian|indonesia|indonesian|lao(?:\s+pdr)?|mongolia|mongolian|"
    r"russia(?:n\s+federation)?|hong\s+kong|viet\s*nam|vietnamese|korea|korean|japan|"
    r"japanese|new\s+zealand|united\s+kingdom|united\s+states)\s+",
    re.IGNORECASE,
)
_ARTICLE_PREFIX = re.compile(r"\b(?:sections?|secs?|s)\b", re.IGNORECASE)
_ARTICLE_WORD = re.compile(r"\b(?:articles?|arts?)\b", re.IGNORECASE)
_ISO_DATE = re.compile(r"\b(?:19|20)\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\b")
_VERSION_FINGERPRINT = re.compile(
    r"\b(?:compilation|version|revision|revised\s+edition|amendment)"
    r"\s*(?:no\.?\s*)?[a-z]?\d+(?:\.\d+)*\b",
    re.IGNORECASE,
)
_MONTHS = {
    name.casefold(): number
    for number, name in enumerate(
        (
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ),
        1,
    )
}
_TEXT_DATE = re.compile(
    r"\b(?:(\d{1,2})\s+)?(" + "|".join(_MONTHS) + r")\s+((?:19|20)\d{2})\b",
    re.IGNORECASE,
)


@dataclass
class KnownLawEvidence:
    """Structured KNOWN evidence for one canonical law."""

    canonical_law_id: str
    version_dates: set[str] = field(default_factory=set)
    version_tokens: set[str] = field(default_factory=set)
    coverage_cutoffs: set[str] = field(default_factory=set)
    provisions: set[tuple[str, str]] = field(default_factory=set)


def normalize_law_name(name: str) -> str:
    """Collapse a statute title to a stable identity key.

    Drops parentheticals (e.g. ``(Act 777)``), 4-digit years, punctuation and
    case so that "Companies Act 2016 (Act 777)" and "Companies Act" match.
    """

    lowered = (name or "").lower()
    lowered = _PAREN.sub(" ", lowered)
    lowered = _YEAR.sub(" ", lowered)
    lowered = _ACT_NUMBER.sub(" ", lowered)
    lowered = _LEADING_GEO.sub("", lowered.strip())
    return _normalize_words(lowered)


def _normalize_words(value: str) -> str:
    """Normalize words without discarding non-Latin legal text."""

    text = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join("".join(char if char.isalnum() else " " for char in text).split())


def normalize_article(article: str) -> str:
    """Normalize section/article spelling while retaining paragraph numbers."""

    text = unicodedata.normalize("NFKC", article or "").casefold()
    text = _ARTICLE_PREFIX.sub("section", text)
    text = _ARTICLE_WORD.sub("article", text)
    return _normalize_words(text)


def normalized_quote_hash(quote: str) -> str:
    """Return a stable hash after case, punctuation, and spacing normalization."""

    text = unicodedata.normalize("NFKC", quote or "").casefold()
    normalized = _normalize_words(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def normalize_version_date(value: str) -> str:
    """Extract the most precise comparable date token available."""

    value = unicodedata.normalize("NFKC", value or "")
    iso_dates = [match.group(0) for match in _ISO_DATE.finditer(value)]
    if iso_dates:
        return iso_dates[-1]
    text_dates = list(_TEXT_DATE.finditer(value))
    if text_dates:
        day, month, year = text_dates[-1].groups()
        prefix = f"{year}-{_MONTHS[month.casefold()]:02d}"
        return f"{prefix}-{int(day):02d}" if day else prefix
    years = [match.group(0) for match in _YEAR.finditer(value)]
    return years[-1] if years else ""


def normalize_version_token(value: str) -> str:
    """Extract a compilation/revision identifier when no date distinguishes it."""

    matches = list(_VERSION_FINGERPRINT.finditer(value or ""))
    return _normalize_words(matches[-1].group(0)) if matches else ""


def _canonical_id(economy: str, law_name: str) -> str:
    slug = normalize_law_name(law_name).replace(" ", "-")
    return f"{economy.upper()}:{slug}"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def known_evidence_index(
    entries: list[LawEntry] | None = None,
) -> dict[tuple[str, str], KnownLawEvidence]:
    """Build law, version, article, and quote identities for the KNOWN baseline."""

    index: dict[tuple[str, str], KnownLawEvidence] = {}

    def ensure(economy: str, law_name: str, canonical_id: str = "") -> KnownLawEvidence:
        code = economy.upper()
        key = (code, normalize_law_name(law_name))
        evidence = index.get(key)
        if evidence is None:
            evidence = KnownLawEvidence(canonical_id or _canonical_id(code, law_name))
            index[key] = evidence
        elif canonical_id and evidence.canonical_law_id.startswith(f"{code}:"):
            evidence.canonical_law_id = canonical_id
        return evidence

    for record in _read_jsonl(KNOWN_INVENTORY_PATH):
        evidence = ensure(
            record["economy"], record["law_name"], record.get("canonical_law_id", "")
        )
        version = normalize_version_date(
            str(
                record.get("amendment_version_date")
                or record.get("last_amended")
                or record["law_name"]
            )
        )
        if version:
            evidence.version_dates.add(version)
        version_token = normalize_version_token(str(record.get("version") or record["law_name"]))
        if version_token:
            evidence.version_tokens.add(version_token)
        article = normalize_article(str(record.get("article") or ""))
        quote_hash = str(record.get("normalized_quote_hash") or "") or normalized_quote_hash(
            str(record.get("verbatim_snippet") or "")
        )
        if article or quote_hash:
            evidence.provisions.add((article, quote_hash))

    pool = entries if entries is not None else load_library()
    for entry in pool:
        if getattr(entry, "origin", "known") == "discovered":
            continue
        evidence = ensure(entry.economy, entry.law_name, entry.law_id)
        version = normalize_version_date(entry.version)
        if version:
            evidence.version_dates.add(version)
        version_token = normalize_version_token(entry.version)
        if version_token:
            evidence.version_tokens.add(version_token)
        cutoff = normalize_version_date(entry.currency_checked_at)
        if cutoff:
            evidence.coverage_cutoffs.add(cutoff)

    document_ids: dict[str, tuple[str, str]] = {}
    for record in _read_jsonl(GOLDEN_DOCUMENTS_PATH):
        economy = record["country_code"].upper()
        law_name = record["source_legislation"]
        ensure(economy, law_name, record["document_id"])
        document_ids[record["document_id"]] = (economy, law_name)
    for record in _read_jsonl(GOLDEN_CASES_PATH):
        document = document_ids.get(record.get("document_id", ""))
        if document is None:
            continue
        economy, law_name = document
        ensure(economy, law_name).provisions.add(
            (
                normalize_article(record.get("article_clause", "")),
                normalized_quote_hash(record.get("verbatim_quote", "")),
            )
        )
    return index


def load_known_inventory(path: Path | str = KNOWN_INVENTORY_PATH) -> set[tuple[str, str]]:
    """Load the official ESCAP Legal Inventory as ``(economy, normalized law)`` keys.

    Returns an empty set if the distilled inventory is absent, so tagging degrades
    to the curated library baseline rather than erroring.
    """

    path = Path(path)
    if not path.exists():
        return set()
    keys: set[tuple[str, str]] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        keys.add((record["economy"].upper(), normalize_law_name(record["law_name"])))
    return keys


def known_law_index(entries: list[LawEntry] | None = None) -> set[tuple[str, str]]:
    """Identity keys ``(ISO3 economy, normalized law name)`` for KNOWN laws.

    Union of the official ESCAP Legal Inventory (the authoritative KNOWN set) and
    our curated law-library baseline, so a law counts as KNOWN if either source
    already has it.
    """

    pool = entries if entries is not None else load_library()
    # Only KNOWN-baseline library entries count; a cached NEW discovery
    # (origin="discovered") must still be treated as NEW.
    library_keys = {
        (entry.economy.upper(), normalize_law_name(entry.law_name))
        for entry in pool
        if getattr(entry, "origin", "known") != "discovered"
    }
    return library_keys | load_known_inventory()


def is_known_law(economy: str, law_name: str, index: set[tuple[str, str]]) -> bool:
    """True if this economy+law is in the KNOWN baseline index."""

    try:
        code = economy_code(economy)
    except ValueError:
        code = (economy or "").strip().upper()
    return (code, normalize_law_name(law_name)) in index


def _economy_key(economy: str) -> str:
    try:
        return economy_code(economy)
    except ValueError:
        return (economy or "").strip().upper()


def _same_date_granularity(left: str, right: str) -> bool:
    """Treat a year/month token as matching a more precise date with that prefix."""

    return left == right or left.startswith(f"{right}-") or right.startswith(f"{left}-")


def _is_newer_version(candidate_raw: str, candidate_date: str, evidence: KnownLawEvidence) -> bool:
    candidate_token = normalize_version_token(candidate_raw)
    if candidate_token:
        if candidate_token in evidence.version_tokens:
            return False
        if evidence.version_tokens:
            return True
    if not candidate_date:
        return False
    if any(
        _same_date_granularity(candidate_date, known)
        for known in evidence.version_dates
    ):
        return False
    if evidence.coverage_cutoffs and candidate_date <= max(evidence.coverage_cutoffs):
        return False
    return bool(evidence.version_dates) and candidate_date > max(evidence.version_dates)


def classify_novelty(
    row: SubmissionRow,
    index: dict[tuple[str, str], KnownLawEvidence],
) -> tuple[str, dict[str, str]]:
    """Classify one row and return its provision-level evidence identity."""

    code = _economy_key(row.economy)
    law_key = (code, normalize_law_name(row.law_name))
    evidence = index.get(law_key)
    article = normalize_article(row.article)
    quote_hash = normalized_quote_hash(row.verbatim_snippet)
    version_raw = row.amendment_version_date or row.last_amended
    version = normalize_version_date(version_raw)
    canonical_id = evidence.canonical_law_id if evidence else _canonical_id(code, row.law_name)
    identity = {
        "canonical_law_id": canonical_id,
        "amendment_version_date": row.amendment_version_date or row.last_amended,
        "normalized_article": article,
        "normalized_quote_hash": quote_hash,
    }

    if row.retrieval_method.strip().lower() in {"fixture", "fallback"}:
        return "KNOWN", identity
    if evidence is None:
        return "NEW_LAW", identity
    if _is_newer_version(version_raw, version, evidence):
        return "NEW_AMENDMENT", identity
    if not article and not quote_hash:
        # There is not enough provision evidence to claim finer-grained novelty.
        return "KNOWN", identity
    if (article, quote_hash) in evidence.provisions:
        return "KNOWN", identity
    return "NEW_PROVISION", identity


def reconcile_discovery_tags(
    rows: list[SubmissionRow],
    *,
    entries: list[LawEntry] | None = None,
) -> list[SubmissionRow]:
    """Return rows with ``discovery_tag`` set from the KNOWN baseline (evidence-based).

    A provision whose law is in the ESCAP inventory/local library is KNOWN;
    everything else is a genuine NEW find, regardless of which live adapter
    surfaced it. Fixture and fixture-fallback sources are also never labelled
    NEW because they are configured evidence, not independent discoveries.
    """

    index = known_evidence_index(entries)
    reconciled: list[SubmissionRow] = []
    for row in rows:
        novelty_type, identity = classify_novelty(row, index)
        reconciled.append(row.model_copy(update={
            "discovery_tag": "KNOWN" if novelty_type == "KNOWN" else "NEW",
            "novelty_type": novelty_type,
            **identity,
        }))
    return reconciled


def reconcile_submission_tags(
    rows: list[SubmissionRow],
    *,
    entries: list[LawEntry] | None = None,
) -> list[SubmissionRow]:
    """Reconcile detailed novelty while preserving the law-level CSV contract.

    ``novelty_type`` records provision/amendment-level discoveries in extended
    JSON metadata. The frozen ``discovery_tag`` column remains law-level:
    provisions from an inventoried law are KNOWN, as are fixture/fallback rows.
    Only laws absent from the official inventory and curated library are NEW.
    """

    reconciled = reconcile_discovery_tags(rows, entries=entries)
    law_index = known_law_index(entries)
    submission_rows: list[SubmissionRow] = []
    for row in reconciled:
        fixture_source = row.retrieval_method.strip().lower() in {"fixture", "fallback"}
        tag = (
            "KNOWN"
            if fixture_source or is_known_law(row.economy, row.law_name, law_index)
            else "NEW"
        )
        submission_rows.append(
            row if row.discovery_tag == tag else row.model_copy(update={"discovery_tag": tag})
        )
    return submission_rows


def summarize_discovery(rows: list[SubmissionRow]) -> dict:
    """Count NEW vs KNOWN and list the distinct laws behind each."""

    def _laws(subset: list[SubmissionRow]) -> list[dict]:
        by_law: dict[tuple[str, str], set[str]] = {}
        for r in subset:
            by_law.setdefault((r.economy, r.law_name), set()).add(r.indicator_id)
        return [
            {"economy": econ, "law_name": law, "indicators": sorted(inds)}
            for (econ, law), inds in sorted(by_law.items())
        ]

    new_rows = [r for r in rows if r.discovery_tag == "NEW"]
    known_rows = [r for r in rows if r.discovery_tag == "KNOWN"]
    return {
        "total_provisions": len(rows),
        "new_provisions": len(new_rows),
        "known_provisions": len(known_rows),
        "novelty_types": {
            novelty_type: sum(r.novelty_type == novelty_type for r in rows)
            for novelty_type in ("KNOWN", "NEW_LAW", "NEW_AMENDMENT", "NEW_PROVISION")
        },
        "new_laws": _laws(new_rows),
        "known_laws": _laws(known_rows),
    }


def build_discovery_report(
    economy: str,
    rows: list[SubmissionRow],
    *,
    entries: list[LawEntry] | None = None,
) -> dict:
    """Reconcile tags, summarize, and attach the human-review gate.

    The returned ``rows`` are tag-reconciled; ``summary`` counts NEW vs KNOWN; and
    ``review_gate`` states that each NEW find is a draft for legal verification.
    """

    reconciled = reconcile_discovery_tags(rows, entries=entries)
    summary = summarize_discovery(reconciled)

    # Group NEW rows into one candidate per distinct LAW (a live sweep surfaces
    # the same statute from many chunks — 15 near-identical "PDPA 2010" rows is
    # noise for a legal reviewer). Key by normalized law name; aggregate the
    # indicators it touches; keep the longest verbatim quote + a source URL as
    # the representative evidence. This is the reviewer-facing candidate list.
    grouped: dict[str, dict] = {}
    for r in reconciled:
        if r.discovery_tag != "NEW" or not (r.law_name or "").strip():
            continue
        key = normalize_law_name(r.law_name)
        cand = grouped.get(key)
        if cand is None:
            grouped[key] = {
                "economy": r.economy,
                "law_name": r.law_name,
                "indicators": [r.indicator_id],
                "article": r.article,
                "verbatim_snippet": r.verbatim_snippet,
                "source_url": r.source_url,
                "confidence": r.confidence,
                "novelty_type": r.novelty_type,
                "canonical_law_id": r.canonical_law_id,
                "amendment_version_date": r.amendment_version_date,
                "evidence_rows": 1,
            }
        else:
            cand["evidence_rows"] += 1
            if r.indicator_id not in cand["indicators"]:
                cand["indicators"].append(r.indicator_id)
            if len(r.verbatim_snippet or "") > len(cand["verbatim_snippet"] or ""):
                cand["verbatim_snippet"] = r.verbatim_snippet
                cand["article"] = r.article
            if not cand["source_url"] and r.source_url:
                cand["source_url"] = r.source_url

    new_candidates = sorted(
        grouped.values(), key=lambda c: (-c["evidence_rows"], c["law_name"].lower())
    )
    for c in new_candidates:
        c["indicators"].sort()

    return {
        "economy": economy,
        "summary": summary,
        "new_candidates": new_candidates,
        "review_gate": (
            "Each NEW discovery is a draft lead for legal review, not a settled "
            "legal conclusion. Verify the verbatim quote and citation against the "
            "official source before the mapping is relied on."
        ),
        "rows": reconciled,
    }
