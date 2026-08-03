#!/usr/bin/env python3
"""Replay extraction for ONE (economy, indicator) corpus text and show the raw
LLM output + which downstream gate kills each row. Empirical kill-layer probe.

Usage: python3 scripts/replay_one_cell.py CHN 10.2
"""
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "ai-service"))
os.chdir(REPO)

from dotenv import load_dotenv

load_dotenv(REPO / ".env")

from providers import get_provider  # noqa: E402
from chunker import regex_legal_chunker  # noqa: E402
from classifier import classify_indicator_candidates  # noqa: E402
from features import get_feature_spec  # noqa: E402


def main():
    economy, indicator = sys.argv[1], sys.argv[2]
    entries = []
    for line in open("data/round2_corpus/manifest.jsonl"):
        d = json.loads(line)
        if d.get("economy") == economy and str(d.get("indicator_id")) == indicator:
            entries.append(d)
    if not entries:
        print("no manifest entry"); return

    provider = get_provider("deepseek")
    spec = get_feature_spec(indicator)
    print(f"feature_spec keys: {list(spec.keys())}")

    for entry in entries:
        text = Path(entry["text_path"]).read_text(errors="replace")
        print(f"\n=== {entry['law_name'][:60]} ({len(text)} chars) ===")
        chunks = regex_legal_chunker(text)
        print(f"chunks: {len(chunks)}")
        for i, ch in enumerate(chunks):
            cands = [c.indicator_id for c in classify_indicator_candidates(ch.text)]
            hit = indicator in cands
            print(f"chunk {i}: {len(ch.text)} chars, candidates={cands}, target_hit={hit}")
            if not hit:
                continue
            raw = provider.extract_features(ch.text, indicator, spec)
            print("RAW EXTRACTION:")
            print(json.dumps(raw, ensure_ascii=False, indent=1)[:1500])
            q = raw.get("verbatim_quote", "")
            if not q:
                print(">>> KILL LAYER: LLM returned empty verbatim_quote")
                continue
            if q not in ch.text:
                print(">>> KILL LAYER: quote not a substring of chunk (verify would drop)")
                continue
            print(f">>> quote OK ({len(q)} chars); now probing submission gates…")
            from submission.schema import SubmissionRow, validate_submission_rows
            row = SubmissionRow(
                economy={"CHN": "China", "LAO": "Lao PDR", "RUS": "Russian Federation",
                         "IDN": "Indonesia", "IND": "India", "MNG": "Mongolia",
                         "THA": "Thailand"}.get(economy, economy),
                law_name=entry["law_name"].split(";")[0].strip(),
                indicator_id=f"P{indicator.split('.')[0]}-I{indicator.split('.', 1)[1]}",
                article=raw.get("article_clause", ""),
                verbatim_snippet=q,
                source_url=(entry.get("urls") or [""])[0],
            )
            kept = validate_submission_rows([row], allow_empty=True)
            print(f">>> submission gates: {'KEPT' if kept else 'DROPPED (see warnings above)'}")


if __name__ == "__main__":
    main()
