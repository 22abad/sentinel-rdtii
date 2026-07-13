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

from .schema import (
    CSV_COLUMNS,
    SubmissionRow,
    discovery_tag_for_method,
    indicator_to_rdtii_code,
)
from .writer import write_csv, write_json, write_outputs

__all__ = [
    "CSV_COLUMNS",
    "SubmissionRow",
    "discovery_tag_for_method",
    "indicator_to_rdtii_code",
    "write_csv",
    "write_json",
    "write_outputs",
]
