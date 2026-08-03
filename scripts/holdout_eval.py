#!/usr/bin/env python3
"""Hold-out evaluation harness — the judge simulation for S3 gates G2-G4.

Reads the ground truth (data/holdout/holdout_countries.jsonl) that the ENGINE
never sees, runs the autonomous path, and scores it:

  --gate 2   portal discovery: bootstrap must find >=1 allowlisted official
             domain per country. PASS = >=4/5 countries.
  --gate 3   P6/P7 end-to-end: >=5 verbatim-verified evidence rows, zero
             manual steps. PASS = >=3/5 countries.   (runs the full pipeline)
  --gate 4   12-pillar direct scoring on one chosen country.

Each run writes a timestamped scorecard to outputs/holdout/ — the evidence
chain for the finale's "autonomous generalization" claim.

Usage:
    python3 scripts/holdout_eval.py --gate 2
    python3 scripts/holdout_eval.py --gate 2 --country Vietnam
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "ai-service"))

from dotenv import load_dotenv

load_dotenv(REPO / ".env")

GROUND_TRUTH = REPO / "data/holdout/holdout_countries.jsonl"
OUT_DIR = REPO / "outputs/holdout"


def load_ground_truth() -> list[dict]:
    return [
        json.loads(line)
        for line in GROUND_TRUTH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


async def gate2(countries: list[dict]) -> dict:
    from discovery.bootstrap import bootstrap_country

    results = []
    for gt in countries:
        t0 = time.time()
        entry = {"country": gt["name"], "iso3": gt["iso3"]}
        try:
            result = await bootstrap_country(gt["name"])
            found = sorted({d for s in result.sources for d in s.domains})
            allow = set(gt["official_domains"])
            matched = sorted(
                d for d in found
                if d in allow or any(d.endswith("." + a) or a.endswith("." + d) for a in allow)
            )
            entry.update({
                "discovered_domains": found,
                "allowlist_matches": matched,
                "hit": bool(matched),
                "seconds": round(time.time() - t0, 1),
            })
        except Exception as exc:  # noqa: BLE001
            entry.update({"error": str(exc)[:200], "hit": False})
        results.append(entry)
        status = "✅" if entry.get("hit") else "❌"
        print(f'{status} {gt["name"]:22s} found={entry.get("discovered_domains", [])} '
              f'matched={entry.get("allowlist_matches", [])}')

    hits = sum(1 for r in results if r.get("hit"))
    passed = hits >= 4
    return {
        "gate": 2,
        "criterion": ">=4/5 countries: bootstrap finds >=1 allowlisted official domain",
        "hits": hits,
        "total": len(results),
        "passed": passed,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", type=int, required=True, choices=[2, 3, 4])
    parser.add_argument("--country", help="restrict to one hold-out country")
    args = parser.parse_args()

    countries = load_ground_truth()
    if args.country:
        countries = [c for c in countries
                     if args.country.lower() in (c["name"].lower(), c["iso3"].lower())]
        if not countries:
            raise SystemExit(f"{args.country!r} not in the hold-out set")

    if args.gate == 2:
        scorecard = asyncio.run(gate2(countries))
    else:
        raise SystemExit(f"gate {args.gate} harness not implemented yet — build it "
                         "AFTER the previous gate passes (S3-1 rule)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    out = OUT_DIR / f"gate{args.gate}_{stamp}.json"
    out.write_text(json.dumps(scorecard, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\ngate {args.gate}: {'PASS ✅' if scorecard['passed'] else 'FAIL ❌'} "
          f"({scorecard['hits']}/{scorecard['total']}) -> {out}")
    sys.exit(0 if scorecard["passed"] else 1)


if __name__ == "__main__":
    main()
