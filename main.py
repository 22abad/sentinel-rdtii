#!/usr/bin/env python3
"""SENTINEL — UN Digital Trade AI Mapper (judges' CLI entrypoint).

Round 1 contract (see requirements/README_template.md):

    python main.py --economy Singapore --pillar 6

Writes ``outputs/<Economy>_P<pillar>_<timestamp>.csv`` and ``.json`` with the
frozen 13-field schema. The same engine that powers the web app is reused here;
this file only wires the CLI to the submission adapter.

The LLM provider is selected from the environment (No Vendor Lock-in):

    RDTII_LLM_PROVIDER=ollama   # or openai, deepseek, mistral, gemini, claude
    OLLAMA_MODEL=qwen2.5:14b
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent
AI_SERVICE = REPO_ROOT / "ai-service"
if str(AI_SERVICE) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE))

load_dotenv(REPO_ROOT / ".env")


def _parse_pillars(token: str) -> list[int]:
    """Turn the --pillar argument into pillar ids.

    Round 2 spans all 12 pillars: accepts a single pillar ("7"), a comma list
    ("6,7,12"), "all" (1-12), or "round1" (the Round 1 scope, pillars 6-7).
    """

    token = token.strip().lower()
    if token == "all":
        return list(range(1, 13))
    if token == "round1":
        return [6, 7]
    try:
        pillars = sorted({int(part) for part in token.split(",") if part.strip()})
    except ValueError:
        pillars = []
    if pillars and all(1 <= p <= 12 for p in pillars):
        return pillars
    raise argparse.ArgumentTypeError(
        "--pillar must be 1-12, a comma list like 6,7, 'all', or 'round1'"
    )


def _pillar_label(pillars: list[int]) -> str:
    """Filename-safe label for one or more pillars (6, 7, or 6-7)."""

    return "-".join(str(p) for p in pillars)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="RDTII evidence discovery + indicator mapping (Pillars 6/7).",
    )
    parser.add_argument("--economy", required=True, help="Economy name or ISO-3 code, e.g. Singapore / SGP")
    parser.add_argument("--pillar", type=_parse_pillars, default=[6, 7], help="1-12, comma list (6,7), all, or round1")
    parser.add_argument("--pdf", default=None, help="Extract from this PDF path (bypasses the crawler)")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Serve official texts from the local law library (no network crawl); "
             "recommended for reproducible / air-gapped runs",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Skip the known-good seed pass and go straight to live discovery. "
             "By default a run seeds from the local library first, then falls "
             "back to discovery (seed-first hybrid).",
    )
    parser.add_argument(
        "--strict-live",
        action="store_true",
        help="Review mode: pure live discovery only; rejects fixtures, mock candidates, "
             "unverified/off-domain documents, and fails explicitly when no live evidence passes.",
    )
    parser.add_argument("--indicators", nargs="*", default=None, help="Restrict to specific indicators, e.g. 6.1 6.4")
    parser.add_argument("--output-dir", default="outputs", help="Directory for CSV/JSON output")
    parser.add_argument("--format", choices=("csv", "json", "both"), default="both")
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow empty output files for research/debugging. By default, a run "
             "with no verified provisions fails without writing output.",
    )
    parser.add_argument("--provider", default=None, help="Override RDTII_LLM_PROVIDER for this run")
    parser.add_argument("--limit", type=int, default=20, help="Max discovery candidates per pillar")
    parser.add_argument("--max-documents", type=int, default=None, help="Cap documents processed per pillar")
    parser.add_argument(
        "--registry-backend",
        choices=("file", "database"),
        default="file",
        help="Discovery source registry (default: checked-in file; database is for the full app)",
    )
    return parser.parse_args(argv)


def _formats(choice: str) -> tuple[str, ...]:
    return ("csv", "json") if choice == "both" else (choice,)


async def _run(args: argparse.Namespace) -> int:
    # The judge CLI is DB-free by default, while the full web app keeps the
    # registry module's database default. Set the CLI choice explicitly before
    # any deferred Discovery imports occur.
    os.environ["DISCOVERY_REGISTRY_BACKEND"] = args.registry_backend
    # Internal callers and tests may construct a partial Namespace instead of
    # going through parse_args(), so optional flags need a safe default.
    strict_live = getattr(args, "strict_live", False)
    if strict_live and (args.offline or args.pdf):
        raise ValueError("--strict-live cannot be combined with --offline or --pdf")

    from submission import (
        SubmissionRow,
        cap_rows_per_law,
        cap_rows_per_law_indicator,
        dedupe_submission_rows,
        reconcile_submission_tags,
        write_outputs,
    )
    from submission.pipeline import (
        discover_and_extract,
        run_library,
        run_pdf,
        run_seed_first,
    )
    from submission.schema import economy_display_name, validate_submission_rows

    display = economy_display_name(args.economy)
    all_rows: list[SubmissionRow] = []
    combined_meta: dict = {
        "economy": display,
        "pillars": args.pillar,
        "retrieval_mode": (
            "strict_live"
            if strict_live
            else "live_discovery"
            if args.no_seed
            else "provided_pdf"
            if args.pdf
            else "seed"
            if args.offline
            else "seed_first"
        ),
        "evidence_counts": {"seed": 0, "live_discovered": 0, "fixture": 0},
        "runs": [],
    }

    for pillar in args.pillar:
        if args.pdf:
            rows, meta = await run_pdf(
                args.economy, pillar, args.pdf,
                provider_name=args.provider, indicators=args.indicators,
            )
        elif args.offline:
            rows, meta = await run_library(
                args.economy, pillar,
                provider_name=args.provider, indicators=args.indicators,
            )
        elif strict_live or args.no_seed:
            rows, meta = await discover_and_extract(
                args.economy, pillar,
                provider_name=args.provider, indicators=args.indicators,
                limit=args.limit, max_documents=args.max_documents,
                strict_live=strict_live,
            )
        else:
            rows, meta = await run_seed_first(
                args.economy, pillar,
                provider_name=args.provider, indicators=args.indicators,
                limit=args.limit, max_documents=args.max_documents,
            )
        combined_meta["runs"].append(meta)
        for mode, count in meta.get("evidence_counts", {}).items():
            combined_meta["evidence_counts"][mode] = (
                combined_meta["evidence_counts"].get(mode, 0) + int(count)
            )
        all_rows.extend(rows)
        print(f"  Pillar {pillar}: {meta['provisions_mapped']} provisions mapped "
              f"({meta.get('documents_processed', 'n/a')} documents)")
        usage = meta.get("usage") or {}
        if usage.get("llm_calls"):
            print(f"    Measured cost: {usage.get('llm_calls', 0)} LLM calls, "
                  f"{usage.get('input_tokens', 0):,} in / {usage.get('output_tokens', 0):,} out tokens, "
                  f"${usage.get('cost_usd', 0.0):.4f}")
        print(f"    Retrieval mode: {meta.get('retrieval_mode', 'unknown')}")
        for warning in meta.get("warnings", []):
            print(f"    ⚠ {warning}")

    if strict_live and not all_rows:
        raise ValueError(
            "Strict live discovery failed: live discovery produced no formally "
            "submittable evidence. No output files were written."
        )

    counts = combined_meta["evidence_counts"]
    print(f"\nSeed evidence: {counts['seed']}")
    print(f"Live-discovered evidence: {counts['live_discovered']}")
    print(f"Fixture evidence: {counts['fixture']}")
    # Discovery methods describe how a candidate was surfaced, not whether its
    # law is novel. Make the ESCAP inventory/library baseline authoritative at
    # the final submission boundary, after rows from every pillar/path have
    # been combined and immediately before CSV/JSON serialization.
    all_rows = reconcile_submission_tags(all_rows)
    all_rows = dedupe_submission_rows(all_rows)
    all_rows = cap_rows_per_law_indicator(all_rows)
    all_rows = cap_rows_per_law(all_rows)
    all_rows = validate_submission_rows(
        all_rows,
        allow_empty=getattr(args, "allow_empty", False),
    )

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    written = write_outputs(
        all_rows,
        economy=display,
        pillar=_pillar_label(args.pillar),
        timestamp=timestamp,
        output_dir=args.output_dir,
        formats=_formats(args.format),
        meta=combined_meta,
    )

    print(f"\n✅ {len(all_rows)} provisions written for {display} (Pillar {_pillar_label(args.pillar)}):")
    for fmt, path in written.items():
        print(f"   {fmt.upper()}: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print(f"SENTINEL — mapping {args.economy}, Pillar {_pillar_label(args.pillar)} …")
    try:
        return asyncio.run(_run(args))
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        # Judges stress-test with bad inputs — a clean message beats a traceback.
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
