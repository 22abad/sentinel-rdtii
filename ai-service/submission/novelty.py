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

import json
import re
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

_PAREN = re.compile(r"\(.*?\)")
_YEAR = re.compile(r"\b\d{4}\b")
_NON_WORD = re.compile(r"[^a-z0-9一-鿿]+")


def normalize_law_name(name: str) -> str:
    """Collapse a statute title to a stable identity key.

    Drops parentheticals (e.g. ``(Act 777)``), 4-digit years, punctuation and
    case so that "Companies Act 2016 (Act 777)" and "Companies Act" match.
    """

    lowered = (name or "").lower()
    lowered = _PAREN.sub(" ", lowered)
    lowered = _YEAR.sub(" ", lowered)
    lowered = _NON_WORD.sub(" ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


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

    index = known_law_index(entries)
    reconciled: list[SubmissionRow] = []
    for row in rows:
        fixture_source = row.retrieval_method.strip().lower() in {"fixture", "fallback"}
        tag = (
            "KNOWN"
            if fixture_source or is_known_law(row.economy, row.law_name, index)
            else "NEW"
        )
        reconciled.append(
            row if row.discovery_tag == tag else row.model_copy(update={"discovery_tag": tag})
        )
    return reconciled


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
    return {
        "economy": economy,
        "summary": summary,
        "new_candidates": [
            {
                "economy": r.economy,
                "law_name": r.law_name,
                "indicator_id": r.indicator_id,
                "article": r.article,
                "verbatim_snippet": r.verbatim_snippet,
                "source_url": r.source_url,
                "confidence": r.confidence,
            }
            for r in reconciled
            if r.discovery_tag == "NEW"
        ],
        "review_gate": (
            "Each NEW discovery is a draft lead for legal review, not a settled "
            "legal conclusion. Verify the verbatim quote and citation against the "
            "official source before the mapping is relied on."
        ),
        "rows": reconciled,
    }
