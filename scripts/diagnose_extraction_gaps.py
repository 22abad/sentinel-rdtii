#!/usr/bin/env python3
"""Diagnose WHERE each gap cell dies in the pipeline (offline, no LLM).

For every gap cell (economy, indicator) from the coverage worklist:
  1. Find corpus manifest entries hinted at that cell (or same economy whose
     text might carry it).
  2. Chunk the text and run the keyword classifier on every chunk.
  3. Report the kill stage:
       NO_TEXT       - no corpus entry for the cell at all
       EMPTY_TEXT    - entry exists but file missing/empty
       NO_CANDIDATE  - text never produces the target indicator as a candidate
                       (=> keyword gap; fix classifier phrases)
       CANDIDATE_OK  - classifier fires; the row dies later (extract/verify/
                       eligibility gates) => needs per-cell extraction debug

Same empirical spirit as scan_gate_misses.py: measure, don't guess.

Usage: python3 scripts/diagnose_extraction_gaps.py [gaps.csv]
       (default: regenerate via tools/coverage_report.py first)
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "ai-service"))

from chunker import regex_legal_chunker  # noqa: E402
from classifier import classify_indicator_candidates  # noqa: E402

MANIFEST = REPO / "data/round2_corpus/manifest.jsonl"
_CHUNK_CACHE: dict[str, list] = {}


def load_manifest():
    by_cell = defaultdict(list)
    by_econ = defaultdict(list)
    for line in MANIFEST.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        by_cell[(d.get("economy"), str(d.get("indicator_id")))].append(d)
        by_econ[d.get("economy")].append(d)
    return by_cell, by_econ


def read_text(entry):
    p = REPO / entry.get("text_path", "")
    if not p.exists():
        return ""
    try:
        return p.read_text(errors="replace")
    except OSError:
        return ""


def diagnose_cell(economy, indicator, by_cell, by_econ):
    entries = by_cell.get((economy, indicator), [])
    scope = "hinted"
    if not entries:
        entries = by_econ.get(economy, [])
        scope = "economy-wide"
    if not entries:
        return {"stage": "NO_TEXT", "scope": scope}

    best = None
    total_chunks = 0
    candidate_chunks = 0
    nonempty = 0
    too_large = 0
    for entry in entries:
        text = read_text(entry)
        if not text.strip():
            continue
        if len(text) > 1_000_000:
            # multi-MB Lao/Thai dumps stall the regex chunker for minutes and
            # are the known language-quality cases anyway — report, don't hang
            too_large += 1
            continue
        nonempty += 1
        path = entry.get("text_path", "")
        if path not in _CHUNK_CACHE:
            chunks = regex_legal_chunker(text)
            _CHUNK_CACHE[path] = [
                (ch.text, classify_indicator_candidates(ch.text)) for ch in chunks
            ]
        cached = _CHUNK_CACHE[path]
        total_chunks += len(cached)
        for _chtext, cands in cached:
            for c in cands:
                if c.indicator_id == indicator:
                    candidate_chunks += 1
                    if best is None or c.retrieval_score > best["score"]:
                        best = {
                            "score": c.retrieval_score,
                            "rule": c.matched_rule,
                            "span": c.matched_span[:80],
                            "law": str(entry.get("law_name", ""))[:60],
                        }
    if nonempty == 0:
        if too_large:
            return {"stage": "TOO_LARGE", "scope": scope, "docs": too_large}
        return {"stage": "EMPTY_TEXT", "scope": scope}
    if best is None:
        return {
            "stage": "NO_CANDIDATE",
            "scope": scope,
            "docs": nonempty,
            "chunks": total_chunks,
        }
    return {
        "stage": "CANDIDATE_OK",
        "scope": scope,
        "docs": nonempty,
        "chunks": total_chunks,
        "candidate_chunks": candidate_chunks,
        "best": best,
    }


def main():
    gaps_csv = sys.argv[1] if len(sys.argv) > 1 else "/tmp/gaps_now.csv"
    by_cell, by_econ = load_manifest()
    rows = list(csv.DictReader(open(gaps_csv)))
    stages = defaultdict(list)
    for r in rows:
        econ, ind, cause = r["economy"], r["indicator"], r["cause"]
        d = diagnose_cell(econ, ind, by_cell, by_econ)
        d["cause"] = cause
        stages[d["stage"]].append((econ, ind, d))
        best = d.get("best")
        detail = (
            f' best={best["score"]:.2f} rule="{best["rule"]}" law="{best["law"]}"'
            if best
            else f' docs={d.get("docs", 0)} chunks={d.get("chunks", 0)}'
        )
        print(f'{econ} {ind:8s} {cause:15s} -> {d["stage"]:13s} [{d["scope"]}]{detail}')

    print("\n=== summary ===")
    for stage, cells in sorted(stages.items()):
        print(f"{stage}: {len(cells)}")
        for econ, ind, d in cells:
            print(f"  {econ} {ind}")


if __name__ == "__main__":
    main()
