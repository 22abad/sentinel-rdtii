#!/usr/bin/env python3
"""Measure runtime, token usage, and API cost for one real document."""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SERVICE = REPO_ROOT / "ai-service"
if str(AI_SERVICE) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE))

from benchmarking.pipeline_runner import run_document_benchmark  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark one real legal document.")
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = asyncio.run(run_document_benchmark(
            repo_root=REPO_ROOT,
            source_url=args.source_url,
            document_id=args.document_id,
            provider_name=args.provider,
            model_name=args.model,
            output_path=args.output.resolve(),
            command=shlex.join(["python", *sys.argv]),
        ))
    except Exception as exc:
        print(f"document benchmark failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "json_report": str(args.output.resolve()),
        "markdown_report": str(args.output.resolve().with_suffix(".md")),
        "pages": report["document"]["pages"],
        "total_cost_usd": report["cost_usd"]["total"],
        "total_seconds": report["timing_seconds"]["total"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
