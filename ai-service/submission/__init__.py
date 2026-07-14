"""Submission adapter layer — UN Global Hackathon Round 1 contract.

The judges validate a fixed 13-column CSV (exact order) plus a JSON file with
extended metadata. This package converts the internal extraction/discovery
results into that exact contract. Nothing here changes the core engine; it is a
thin, deterministic adapter so the same pipeline can also serve the judges' CLI:

    python main.py --economy Singapore --pillar 6

Modules:
- schema.py  — SubmissionRow model, CSV column order, indicator-code + tag logic
- writer.py  — CSV (utf-8-sig, fixed order) and JSON writers
- pipeline.py — orchestrates discovery -> fetch -> extract -> rows
"""

from .novelty import (
    build_discovery_report,
    reconcile_discovery_tags,
    reconcile_submission_tags,
    summarize_discovery,
)
from .schema import (
    CSV_COLUMNS,
    REQUIRED_SUBMISSION_FIELDS,
    SubmissionRow,
    discovery_tag_for_method,
    indicator_to_rdtii_code,
    validate_submission_rows,
)
from .writer import write_csv, write_json, write_outputs

__all__ = [
    "CSV_COLUMNS",
    "REQUIRED_SUBMISSION_FIELDS",
    "SubmissionRow",
    "build_discovery_report",
    "discovery_tag_for_method",
    "indicator_to_rdtii_code",
    "validate_submission_rows",
    "reconcile_discovery_tags",
    "reconcile_submission_tags",
    "summarize_discovery",
    "write_csv",
    "write_json",
    "write_outputs",
]
