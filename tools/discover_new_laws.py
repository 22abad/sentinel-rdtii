#!/usr/bin/env python3
"""Sweep for NEW laws and write a human-review discovery report.

Hackathon discovery bonus — reward independently finding in-force Pillar 6/7 laws
beyond the provided sample kit:

    python tools/discover_new_laws.py --economy Singapore --pillar all

Runs the live discovery + mapping pipeline, then reconciles every mapped
provision against the curated KNOWN baseline (the local law library): a law
absent from the baseline is a genuine NEW find. Writes a report to
``logs/discovery_report.json`` listing NEW candidates with their audit trail
(source URL, verbatim quote, indicator, confidence) so a lawyer can verify each
one — following the "draft for review" guardrail: a NEW find is a lead, not a
settled legal conclusion.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SERVICE = REPO_ROOT / "ai-service"
if str(AI_SERVICE) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE))

load_dotenv(REPO_ROOT / ".env")


def _pillars(token: str) -> list[int]:
    token = token.strip().lower()
    if token == "all":
        return [6, 7]
    if token in {"6", "7"}:
        return [int(token)]
    raise argparse.ArgumentTypeError("--pillar must be 6, 7, or all")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="discover_new_laws.py", description=__doc__)
    parser.add_argument("--economy", required=True, help="Economy name or ISO-3 code")
    parser.add_argument("--pillar", type=_pillars, default=[6, 7], help="6, 7, or all")
    parser.add_argument("--indicators", nargs="*", default=None, help="Restrict indicators, e.g. 6.1 6.4")
    parser.add_argument("--provider", default=None, help="Override RDTII_LLM_PROVIDER")
    parser.add_argument("--limit", type=int, default=20, help="Max discovery candidates per pillar")
    parser.add_argument("--output", default=str(REPO_ROOT / "logs" / "discovery_report.json"))
    return parser.parse_args(argv)


async def _sweep(args: argparse.Namespace) -> dict:
    from submission import build_discovery_report
    from submission.pipeline import discover_and_extract
    from submission.schema import economy_display_name

    rows = []
    warnings: list[str] = []
    for pillar in args.pillar:
        pillar_rows, meta = await discover_and_extract(
            args.economy, pillar,
            provider_name=args.provider, indicators=args.indicators,
            limit=args.limit,
        )
        rows.extend(pillar_rows)
        warnings.extend(meta.get("warnings", []))

    report = build_discovery_report(economy_display_name(args.economy), rows)
    report["warnings"] = warnings
    # The reconciled SubmissionRow objects are not JSON-friendly; drop them here
    # (the summary and new_candidates already carry the reportable content).
    report.pop("rows", None)
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print(f"SENTINEL — NEW-law sweep for {args.economy}, Pillar {args.pillar} …")
    report = asyncio.run(_sweep(args))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    s = report["summary"]
    print(f"  {s['new_provisions']} NEW / {s['known_provisions']} KNOWN provisions "
          f"across {len(s['new_laws'])} new law(s)")
    for law in s["new_laws"]:
        print(f"    NEW: {law['economy']} — {law['law_name']} {law['indicators']}")
    print(f"\n📄 Discovery report (for legal review): {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
