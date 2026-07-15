#!/usr/bin/env python3
"""Refresh committed Round 1 samples with authoritative citation metadata.

The samples are frozen model outputs, so rerunning an LLM merely to repair
metadata would make the review artifact non-deterministic.  This tool enriches
those rows from the checked-in law-library manifest, applies the legal review's
exact section/page corrections, reconciles NEW/KNOWN at the final submission
boundary, and reruns the same quality validator used by ``main.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SERVICE = REPO_ROOT / "ai-service"
sys.path.insert(0, str(AI_SERVICE))

from law_library import load_library  # noqa: E402
from submission.novelty import reconcile_submission_tags  # noqa: E402
from submission.schema import SubmissionRow, extract_year, validate_submission_rows  # noqa: E402
from submission.writer import write_csv, write_json  # noqa: E402

SAMPLE_DIR = REPO_ROOT / "docs" / "r1-submission-sample"

# Exact corrections from the checked-in source text and its page markers.
# Prefixes are deliberately long enough to identify one frozen evidence row.
ARTICLE_OVERRIDES: dict[tuple[str, str], tuple[str, int | None]] = {
    ("Information Privacy Act 2009 (QLD)", "Personal information means information or an opinion"): ("Section 12", 11),
    ("Information Privacy Act 2009 (QLD)", "the kind of personal information accessed, disclosed or lost"): ("Section 48(2)", 26),
    ("Information Privacy Act 2009 (QLD)", "review the application of the exemption each month"): ("Section 60(4)", 37),
    ("Information Privacy Act 2009 (QLD)", "Before giving a direction under subsection (2)"): ("Section 61(5)", 38),
    ("Information Privacy Act 2009 (QLD)", "The functions of an authorised officer"): ("Section 62", 38),
    ("Information Privacy Act 2009 (QLD)", "department or administrative unit within a department"): ("Section 199(4)", 78),
    ("Information Privacy Act 2009 (QLD)", "An agency must take reasonable steps to implement practices"): ("QPP 1.2", 94),
}


def _article_and_page(row: SubmissionRow) -> tuple[str, int | None]:
    for (law_name, quote_prefix), correction in ARTICLE_OVERRIDES.items():
        if row.law_name == law_name and row.verbatim_snippet.startswith(quote_prefix):
            return correction
    if not row.article and row.indicator_id == "P7-I1":
        return "Whole Act (framework-level evidence)", None
    return row.article, None


def _location(row: SubmissionRow, article: str, page: int | None) -> str:
    if page is not None:
        return f"p. {page} ({article})"
    if "#" in row.source_url:
        return row.source_url
    return f"{row.source_url} ({article})" if article else row.source_url


def refresh(path: Path) -> tuple[int, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = load_library()
    by_law = {entry.law_name: entry for entry in entries}
    original = [SubmissionRow.model_validate(record) for record in payload["provisions"]]

    enriched: list[SubmissionRow] = []
    for row in original:
        entry = by_law.get(row.law_name)
        article, page = _article_and_page(row)
        last_amended = extract_year(entry.last_amended) if entry else ""
        enriched.append(row.model_copy(update={
            "article": article,
            "last_amended": last_amended or "Not stated in source",
            "location_reference": _location(row, article, page),
            "amendment_version_date": entry.last_amended if entry else row.amendment_version_date,
        }))

    reconciled = reconcile_submission_tags(enriched, entries=entries)
    valid = validate_submission_rows(reconciled)
    write_json(valid, path, meta=payload.get("meta", {}))
    write_csv(valid, path.with_suffix(".csv"))
    return len(original), len(valid)


def main() -> int:
    for path in sorted(SAMPLE_DIR.glob("*.json")):
        before, after = refresh(path)
        print(f"{path.name}: {before} -> {after} judge-usable rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
