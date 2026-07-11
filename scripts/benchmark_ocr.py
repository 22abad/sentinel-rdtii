#!/usr/bin/env python3
"""Run the reviewed page-level OCR CER benchmark."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SERVICE = REPO_ROOT / "ai-service"
if str(AI_SERVICE) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE))

from benchmarking.ocr_runner import run_ocr_benchmark  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure OCR CER on reviewed pages.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=REPO_ROOT / "evaluation/ocr/cases.jsonl",
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-pending", action="store_true")
    args = parser.parse_args()
    try:
        report = run_ocr_benchmark(
            repo_root=REPO_ROOT,
            source_root=args.source_root,
            cases_path=args.cases.resolve(),
            output_path=args.output.resolve(),
            include_pending=args.include_pending,
            command=shlex.join(["python", *sys.argv]),
        )
    except Exception as exc:
        print(f"OCR benchmark failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "json_report": str(args.output.resolve()),
        "markdown_report": str(args.output.resolve().with_suffix(".md")),
        "pages": report["summary"]["page_count"],
        "macro_cer": report["summary"]["macro_cer"],
        "micro_cer": report["summary"]["micro_cer"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
