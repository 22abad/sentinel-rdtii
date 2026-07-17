#!/usr/bin/env python3
"""Build a reviewer evidence pack: full 13-field rows for chosen indicators.

The self-eval JSONs carry scores but not quotes; a legal reviewer checking a
scenario (economy list x indicator list) needs the verbatim quote, article
and source URL per row. This tool runs the real pipeline over the Round 2
corpus texts of the baseline laws mapped to those indicators and writes the
standard CSV/JSON via the submission writer.

    python tools/build_evidence_pack.py --economies CHN IND THA \
        --indicators 6.1 6.2 7.3 9.3 12.2 12.4.1 12.4.2 --label review
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SERVICE = REPO_ROOT / "ai-service"
if str(AI_SERVICE) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE))
load_dotenv(REPO_ROOT / ".env")

INVENTORY = REPO_ROOT / "data" / "round2_inventory.jsonl"
CORPUS_DIR = REPO_ROOT / "data" / "round2_corpus"

TEXT_CAP = 60_000
CONCURRENCY = 1  # gentle: evidence packs run alongside other jobs


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:80]


async def _build(args: argparse.Namespace) -> None:
    from types import SimpleNamespace

    from providers import resolve_provider
    from services.extraction import run_extraction
    from submission import write_outputs
    from submission.pipeline import build_row
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from run_round2_eval import _load_corpus_index, _select_relevant_text  # noqa: E402

    provider = resolve_provider(args.provider)
    wanted = set(args.indicators)
    # Expand "12.4" style prefixes to their sub-indicators.
    for line in json.loads((REPO_ROOT / "data" / "rdtii21_methodology.json").read_text()):
        if any(line["indicator_id"].startswith(p + ".") for p in wanted):
            wanted.add(line["indicator_id"])

    semaphore = asyncio.Semaphore(CONCURRENCY)
    all_rows = []

    async def _one(economy: str, slug: str, text_path: str, indicators: list[str], law: str, urls: list[str]):
        text = _select_relevant_text(
            (REPO_ROOT / text_path).read_text(encoding="utf-8")[: TEXT_CAP * 4], indicators
        )
        async with semaphore:
            try:
                response = await asyncio.wait_for(
                    run_extraction(text, provider, target_indicators=indicators),
                    timeout=args.timeout,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  [{economy}] {slug[:50]}: {type(exc).__name__}")
                return
        candidate = SimpleNamespace(
            url=urls[0] if urls else "", title=law, last_update="",
            discovery_method="known_mapping", confidence=1.0, warnings=[],
        )
        for m in response.mappings:
            if m.indicator not in wanted:
                continue
            all_rows.append(build_row(
                m, economy_display=economy, candidate=candidate, source_text=text,
                doc_meta={"quality": "good", "retrieval_method": "round2_corpus",
                          "location_reference": urls[0] if urls else text_path},
            ))
        print(f"  [{economy}] {slug[:50]}: {len(response.mappings)} mapping(s)")

    jobs = []
    for economy in args.economies:
        corpus = _load_corpus_index(economy)
        by_doc: dict[str, tuple[list[str], str, list[str]]] = {}
        for line in INVENTORY.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["economy"] != economy.upper() or row["indicator_id"] not in wanted:
                continue
            slug = _slug(row["law_name"])
            if slug not in corpus:
                continue
            inds, law, urls = by_doc.setdefault(slug, ([], row["law_name"], row["urls"]))
            if row["indicator_id"] not in inds:
                inds.append(row["indicator_id"])
        for slug, (inds, law, urls) in by_doc.items():
            jobs.append(_one(economy, slug, corpus[slug], sorted(inds), law, urls))
        print(f"{economy}: {len(by_doc)} documents queued")

    await asyncio.gather(*jobs)

    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    written = write_outputs(
        all_rows, economy=f"{args.label}-pack", pillar="x", timestamp=stamp,
        output_dir=str(REPO_ROOT / "outputs"), formats=("csv", "json"),
        meta={"pack": args.label, "economies": args.economies,
              "indicators": sorted(wanted)},
    )
    print(f"\n{len(all_rows)} evidence rows -> " + ", ".join(str(v) for v in written.values()))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="build_evidence_pack.py", description=__doc__)
    p.add_argument("--economies", nargs="+", required=True)
    p.add_argument("--indicators", nargs="+", required=True)
    p.add_argument("--label", default="evidence")
    p.add_argument("--provider", default="deepseek")
    p.add_argument("--timeout", type=int, default=600)
    args = p.parse_args(argv)
    asyncio.run(_build(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
