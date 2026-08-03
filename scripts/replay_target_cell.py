#!/usr/bin/env python3
"""Corpus-path-faithful replay: run_extraction with target_indicators on the
cell's hinted manifest text, printing mappings AND rejection reasons.

Usage: python3 scripts/replay_target_cell.py RUS 6.3
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "ai-service"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from providers import get_provider  # noqa: E402


async def main():
    economy, indicator = sys.argv[1], sys.argv[2]
    cap = int(sys.argv[3]) if len(sys.argv) > 3 else 60000
    from services.extraction import run_extraction

    provider = get_provider("deepseek")
    for line in (REPO / "data/round2_corpus/manifest.jsonl").read_text().splitlines():
        d = json.loads(line)
        if d.get("economy") != economy or str(d.get("indicator_id")) != indicator:
            continue
        p = REPO / d["text_path"]
        if not p.exists():
            print(f"MISSING FILE: {d['text_path']}")
            continue
        text = p.read_text(errors="replace")
        if len(text) > cap:
            from rag.retriever import select_relevant_text

            text = select_relevant_text(text, [indicator], cap, country_code=economy)
        print(f"\n=== {d['law_name'][:70]} ({len(text)} chars fed) ===")
        result = await run_extraction(text, provider, target_indicators=[indicator])
        print(f"mappings: {len(result.mappings)}  rejected: {len(result.rejected)}")
        for m in result.mappings:
            print("  MAP", m.indicator, "|", (m.verbatim_quote or "")[:90])
        reasons = {}
        for r in result.rejected:
            key = str(getattr(r, "reason", ""))[:120]
            reasons[key] = reasons.get(key, 0) + 1
        for k, n in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"  REJ x{n}: {k}")


asyncio.run(main())
