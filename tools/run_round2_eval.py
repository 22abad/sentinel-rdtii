#!/usr/bin/env python3
"""Round 2 self-evaluation — run the pipeline against the official baseline.

For one economy, every baseline law with a locally fetched text is pushed
through the real extraction pipeline (targeted at the indicators the official
inventory maps it to), the deterministic scorer produces our score, and the
result is compared against the official raw score from the Round 2 database.

    python tools/run_round2_eval.py --economy IND                # full economy
    python tools/run_round2_eval.py --economy IND --pillar 7     # one pillar
    python tools/run_round2_eval.py --economy IND --limit 10     # quick pass

Writes outputs/round2_eval_<ECON>_<timestamp>.json with per-row detail and
prints an accuracy summary (coverage, evidence yield, exact-match rate, MAE).
This is an honest benchmark: rows without local text, failed extractions and
score mismatches are all counted and reported, never hidden.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SERVICE = REPO_ROOT / "ai-service"
if str(AI_SERVICE) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE))
load_dotenv(REPO_ROOT / ".env")

INVENTORY = REPO_ROOT / "data" / "round2_inventory.jsonl"
CORPUS_MANIFEST = REPO_ROOT / "data" / "round2_corpus" / "manifest.jsonl"

TEXT_CAP = 60_000        # total chars per document fed to extraction
WINDOW = 4_000           # relevance-selection window size
DOC_CONCURRENCY = 2      # documents extracted in parallel (deepseek TPM headroom)


def _select_relevant_text(text: str, indicators: list[str]) -> str:
    """Pick the document segments most relevant to the target indicators.

    Long statutes bury the operative clause hundreds of kB in; a blind prefix
    cap never shows it to the model (the India P7 rows all missed this way).
    Windows are scored by indicator phrase hits (same table the classifier
    routes on); the best windows are concatenated up to TEXT_CAP, keeping
    document order. Falls back to the prefix when nothing matches.
    """
    if len(text) <= TEXT_CAP:
        return text
    from classifier import _INDICATOR_PHRASES  # routing phrase table

    phrases: set[str] = set()
    for iid in indicators:
        phrases.update(p.lower() for p in _INDICATOR_PHRASES.get(iid, []))
    windows = [(i, text[i:i + WINDOW]) for i in range(0, len(text), WINDOW)]
    scored = []
    for start, chunk in windows:
        low = chunk.lower()
        hits = sum(low.count(p) for p in phrases if p)
        scored.append((hits, start, chunk))
    ranked = sorted(scored, key=lambda t: (-t[0], t[1]))
    if not ranked or ranked[0][0] == 0:
        return text[:TEXT_CAP]
    picked, budget = [], TEXT_CAP
    for hits, start, chunk in ranked:
        if budget <= 0 or hits == 0:
            break
        picked.append((start, chunk))
        budget -= len(chunk)
    picked.sort()  # restore document order for offset sanity
    return "\n".join(chunk for _start, chunk in picked)


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:80]


def _load_rows(economy: str, pillar: int | None) -> list[dict]:
    rows = []
    for line in INVENTORY.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["economy"] != economy.upper():
            continue
        if pillar is not None and row["pillar"] != pillar:
            continue
        rows.append(row)
    return rows


def _load_corpus_index(economy: str) -> dict[str, str]:
    """slug -> text_path for locally fetched laws of this economy.

    Reads the corpus manifest and additionally scans the economy's corpus
    directory: the fetcher writes its manifest only at the end of a run, so
    a still-running (or interrupted) fetch has texts on disk that the
    manifest does not list yet.
    """
    index: dict[str, str] = {}
    if CORPUS_MANIFEST.exists():
        for line in CORPUS_MANIFEST.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("economy") != economy.upper():
                continue
            if rec.get("status") in ("ok", "cached"):
                index[_slug(rec["law_name"])] = rec["text_path"]
    econ_dir = CORPUS_MANIFEST.parent / economy.upper()
    if econ_dir.is_dir():
        for path in econ_dir.glob("*.txt"):
            if path.stat().st_size > 0:
                index.setdefault(path.stem, str(path.relative_to(REPO_ROOT)))
    return index


async def _evaluate(args: argparse.Namespace) -> dict:
    from providers import resolve_provider
    from services.extraction import run_extraction

    provider = resolve_provider(args.provider)
    rows = _load_rows(args.economy, args.pillar)
    corpus = _load_corpus_index(args.economy)

    # Group baseline rows by document so one extraction evaluates every
    # indicator that law is officially mapped to.
    by_doc: dict[str, list[dict]] = defaultdict(list)
    no_text: list[dict] = []
    for row in rows:
        slug = _slug(row["law_name"])
        if slug in corpus:
            by_doc[slug].append(row)
        else:
            no_text.append(row)

    docs = list(by_doc.items())
    if args.limit:
        docs = docs[: args.limit]

    semaphore = asyncio.Semaphore(DOC_CONCURRENCY)
    results: list[dict] = []

    async def _one(slug: str, doc_rows: list[dict]) -> None:
        text_path = REPO_ROOT / corpus[slug]
        indicators = sorted({r["indicator_id"] for r in doc_rows})
        text = _select_relevant_text(
            text_path.read_text(encoding="utf-8"), indicators
        )
        async with semaphore:
            try:
                response = await asyncio.wait_for(
                    run_extraction(text, provider, target_indicators=indicators),
                    timeout=args.timeout,
                )
                mappings = response.mappings
                error = ""
            except Exception as exc:  # noqa: BLE001 — recorded, not fatal
                mappings, error = [], f"{type(exc).__name__}: {str(exc)[:90]}"
        best: dict[str, float] = {}
        for m in mappings:
            best[m.indicator] = max(best.get(m.indicator, 0.0), float(m.score))
        for row in doc_rows:
            predicted = best.get(row["indicator_id"])
            # RDTII semantics: no qualifying evidence extracted = score 0.
            effective = predicted if predicted is not None else 0.0
            results.append({
                "economy": row["economy"],
                "pillar": row["pillar"],
                "indicator_id": row["indicator_id"],
                "law_name": row["law_name"][:100],
                "official_score": row["official_score"],
                "predicted_score": predicted,
                "effective_score": effective,
                "evidence_found": predicted is not None,
                "exact_match": abs(effective - row["official_score"]) < 1e-9,
                "error": error,
            })
        done = sum(1 for r in results)
        print(f"  [{done} rows done] {slug[:60]}: "
              f"{len(indicators)} indicator(s), {len(mappings)} mapping(s) {error[:40]}")

    await asyncio.gather(*(_one(slug, doc_rows) for slug, doc_rows in docs))

    evaluated = results  # every evaluated row scores (no-evidence = 0.0)
    exact = [r for r in evaluated if r["exact_match"]]
    mae = (sum(abs(r["effective_score"] - r["official_score"]) for r in evaluated)
           / len(evaluated)) if evaluated else None

    per_pillar: dict[int, dict] = {}
    for r in results:
        p = per_pillar.setdefault(r["pillar"], {"rows": 0, "evidence": 0, "exact": 0})
        p["rows"] += 1
        p["evidence"] += int(r["evidence_found"])
        p["exact"] += int(r["exact_match"])

    return {
        "economy": args.economy.upper(),
        "pillar_filter": args.pillar,
        "provider": getattr(provider, "model_name", getattr(provider, "name", "?")),
        "baseline_rows": len(rows),
        "rows_with_local_text": sum(len(v) for v in by_doc.values()),
        "rows_without_local_text": len(no_text),
        "documents_evaluated": len(docs),
        "rows_evaluated": len(results),
        "evidence_yield": sum(1 for r in results if r["evidence_found"]),
        "exact_score_matches": len(exact),
        "exact_match_rate": round(len(exact) / len(evaluated), 3) if evaluated else None,
        "mean_absolute_error": round(mae, 3) if mae is not None else None,
        "per_pillar": {str(k): v for k, v in sorted(per_pillar.items())},
        "rows": results,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="run_round2_eval.py", description=__doc__)
    p.add_argument("--economy", required=True, help="ISO-3, e.g. IND")
    p.add_argument("--pillar", type=int, default=None)
    p.add_argument("--limit", type=int, default=None, help="cap documents evaluated")
    p.add_argument("--provider", default="deepseek")
    p.add_argument("--timeout", type=int, default=600, help="per-document timeout (s)")
    args = p.parse_args(argv)

    t0 = time.time()
    report = asyncio.run(_evaluate(args))
    report["duration_seconds"] = round(time.time() - t0, 1)

    out_dir = REPO_ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_path = out_dir / f"round2_eval_{report['economy']}_{stamp}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n===== ROUND 2 SELF-EVAL =====")
    for key in ("economy", "provider", "baseline_rows", "rows_with_local_text",
                "rows_evaluated", "evidence_yield", "exact_score_matches",
                "exact_match_rate", "mean_absolute_error", "duration_seconds"):
        print(f"  {key}: {report[key]}")
    print("  per_pillar:")
    for pillar, stats in report["per_pillar"].items():
        print(f"    P{pillar}: rows={stats['rows']} evidence={stats['evidence']} exact={stats['exact']}")
    print(f"\n  report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
