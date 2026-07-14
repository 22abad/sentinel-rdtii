#!/usr/bin/env python3
"""Fail when the candidate Golden Set loses its structural coverage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "ai-service"))

from evaluation.coverage import audit_coverage  # noqa: E402
from evaluation.models import GoldenCase, GoldenDocument  # noqa: E402
from evaluation.runner import load_jsonl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    cases = load_jsonl(REPO_ROOT / "evaluation/golden/cases.jsonl", GoldenCase)
    documents = load_jsonl(
        REPO_ROOT / "evaluation/golden/documents.jsonl", GoldenDocument
    )
    audit = audit_coverage(cases, documents, approved_only=args.approved_only)
    if args.json:
        print(json.dumps(audit.as_dict(), indent=2, sort_keys=True))
    else:
        label = "approved" if args.approved_only else "candidate"
        print(
            f"{label}: {audit.case_count} cases, {audit.document_count} documents, "
            f"pending cases={len(audit.pending_case_ids)}, issues={len(audit.issues)}"
        )
        for issue in audit.issues:
            print(f"- {issue}")
    return 0 if audit.structurally_complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
