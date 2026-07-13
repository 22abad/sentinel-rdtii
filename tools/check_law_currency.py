#!/usr/bin/env python3
"""Check whether cached laws are still current at their official source.

Laws get amended and re-compiled; a stale cache silently maps outdated text. This
re-fetches each law in the local library from its official URL (via the project's
own crawler) and compares the live page against the stored version fingerprint —
flagging any law whose recorded version no longer appears, as a lead for review.

    python tools/check_law_currency.py            # check the whole library
    python tools/check_law_currency.py --economy MYS
    # → logs/law_currency_report.json

Modelled on the policy-monitor "sweep" pattern: surface drift for a human to
verify; a flag is a draft lead, not a conclusion.
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="check_law_currency.py", description=__doc__)
    parser.add_argument("--economy", default=None, help="Restrict to one economy (ISO-3), e.g. MYS")
    parser.add_argument("--output", default=str(REPO_ROOT / "logs" / "law_currency_report.json"))
    return parser.parse_args(argv)


async def _check(economy: str | None) -> dict:
    from law_library import assess_currency, load_library
    from services.document_fetch import fetch_document_text

    entries = load_library()
    if economy:
        entries = [e for e in entries if e.economy == economy.strip().upper()]

    results = []
    for e in entries:
        row = {
            "law_id": e.law_id, "economy": e.economy, "law_name": e.law_name,
            "version": e.version, "currency_source": e.currency_source or e.official_url,
            "checked_previously": e.currency_checked_at,
        }
        try:
            doc = await asyncio.wait_for(
                fetch_document_text(row["currency_source"], browser_mode="http"), timeout=90
            )
            assessment = assess_currency(e.version, getattr(doc, "text", "") or "")
            row.update(assessment)
            row["status"] = "current" if assessment["current"] else "review"
        except Exception as exc:  # noqa: BLE001 — one unreachable source must not abort the sweep
            row["status"] = "unreachable"
            row["error"] = f"{type(exc).__name__}: {exc}"
        results.append(row)

    review = [r for r in results if r["status"] != "current"]
    return {
        "checked": len(results),
        "current": sum(r["status"] == "current" for r in results),
        "needs_review": [r["law_id"] for r in review],
        "results": results,
        "review_gate": (
            "A 'review' or 'unreachable' status is a lead for a human to verify the "
            "law's current version at its official source — not proof of change."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print("SENTINEL — checking local law library currency …")
    report = asyncio.run(_check(args.economy))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for r in report["results"]:
        mark = {"current": "✓", "review": "⚠", "unreachable": "?"}.get(r["status"], "?")
        print(f"  {mark} {r['economy']} {r['law_name']} — {r['status']} ({r['version']})")
    print(f"\n{report['current']}/{report['checked']} current. Report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
