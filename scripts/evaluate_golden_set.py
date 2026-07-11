#!/usr/bin/env python3
"""Run the reproducible RDTII golden-set evaluation."""

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

from evaluation.runner import run_evaluation  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate RDTII mappings against human-reviewed golden cases.",
    )
    parser.add_argument(
        "--mode",
        choices=("offline", "live-discovery", "full"),
        required=True,
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=REPO_ROOT / "evaluation/golden/cases.jsonl",
    )
    parser.add_argument(
        "--documents",
        type=Path,
        default=REPO_ROOT / "evaluation/golden/documents.jsonl",
    )
    parser.add_argument(
        "--offline-responses",
        type=Path,
        default=REPO_ROOT / "evaluation/fixtures/offline-provider-responses.jsonl",
    )
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--countries", nargs="*", default=[])
    parser.add_argument("--include-pending", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = asyncio.run(run_evaluation(
            repo_root=REPO_ROOT,
            mode=args.mode,
            cases_path=args.cases.resolve(),
            documents_path=args.documents.resolve(),
            output_path=args.output.resolve(),
            provider_name=args.provider,
            model_name=args.model,
            offline_responses_path=args.offline_responses.resolve(),
            countries=set(args.countries),
            include_pending=args.include_pending,
            command=shlex.join(["python", *sys.argv]),
        ))
    except Exception as exc:
        print(f"evaluation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "mode": report["metadata"]["mode"],
        "json_report": str(args.output.resolve()),
        "markdown_report": str(args.output.resolve().with_suffix(".md")),
        "runtime_seconds": report["runtime_seconds"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
