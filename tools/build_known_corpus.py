#!/usr/bin/env python3
"""Build a local full-text corpus of the KNOWN laws (offline reference / RAG input).

The official ESCAP Legal Inventory lists ~195 KNOWN laws for Singapore, Malaysia
and Australia with an official URL each. This tool fetches each law's text via the
project's own crawler and stores it locally as plain text plus an index manifest,
so the whole KNOWN corpus is available offline (and ready to feed a local RAG).

    python tools/build_known_corpus.py                 # fetch all (resumable)
    python tools/build_known_corpus.py --economy SGP   # one economy
    python tools/build_known_corpus.py --browser       # use the browser path too (slow, JS sites)
    python tools/build_known_corpus.py --limit 20

Text lands in data/known_corpus/<ECON>/<slug>.txt (git-ignored — local/RAG use);
the index (url, sha256, char_count, status) is written to
data/known_corpus/manifest.jsonl. Re-running skips laws already fetched.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SERVICE = REPO_ROOT / "ai-service"
if str(AI_SERVICE) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE))
load_dotenv(REPO_ROOT / ".env")

INVENTORY_CSV = REPO_ROOT / "requirements" / "Singapore, Malaysia, Australia, Legal Inventory.csv"
CORPUS_DIR = REPO_ROOT / "data" / "known_corpus"
_ISO = {"singapore": "SGP", "malaysia": "MYS", "australia": "AUS"}


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:80]


def _laws_from_inventory() -> list[dict]:
    """Distinct (economy, law, url) rows from the official inventory."""
    seen, out = set(), []
    for r in csv.DictReader(INVENTORY_CSV.open(encoding="utf-8-sig")):
        econ = _ISO.get((r["country"] or "").strip().lower())
        name = (r["Act.and.or.practice"] or "").strip()
        urls = re.findall(r"https?://[^\s,;]+", r.get("References") or "")
        if not econ or not name or not urls:
            continue
        key = (econ, name.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({"economy": econ, "law_name": name, "url": urls[0].rstrip(").")})
    return out


async def _build(args: argparse.Namespace) -> dict:
    from services.document_fetch import fetch_document_text

    laws = _laws_from_inventory()
    if args.economy:
        laws = [x for x in laws if x["economy"] == args.economy.upper()]
    if args.limit:
        laws = laws[: args.limit]

    mode = "auto" if args.browser else "http"
    results = []
    for i, law in enumerate(laws, 1):
        econ_dir = CORPUS_DIR / law["economy"]
        econ_dir.mkdir(parents=True, exist_ok=True)
        text_path = econ_dir / f"{_slug(law['law_name'])}.txt"
        row = {**law, "text_path": str(text_path.relative_to(REPO_ROOT))}
        if text_path.exists() and text_path.stat().st_size > 0:  # resumable
            body = text_path.read_text(encoding="utf-8")
            row.update(status="cached", char_count=len(body),
                       sha256=hashlib.sha256(body.encode()).hexdigest())
            results.append(row)
            continue
        try:
            doc = await asyncio.wait_for(fetch_document_text(law["url"], browser_mode=mode), timeout=args.timeout)
            body = getattr(doc, "text", "") or ""
            if len(body) < 500:  # shell/placeholder, not real content
                raise ValueError(f"too short ({len(body)} chars) — likely a JS shell")
            text_path.write_text(body, encoding="utf-8")
            row.update(status="ok", char_count=len(body),
                       sha256=hashlib.sha256(body.encode()).hexdigest())
            print(f"  [{i}/{len(laws)}] OK   {law['economy']} {law['law_name'][:55]} ({len(body)//1000}k)")
        except Exception as exc:  # noqa: BLE001 — one bad source must not stop the corpus
            row.update(status="failed", error=f"{type(exc).__name__}: {str(exc)[:90]}")
            print(f"  [{i}/{len(laws)}] FAIL {law['economy']} {law['law_name'][:55]} — {row['error'][:50]}")
        results.append(row)

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    (CORPUS_DIR / "manifest.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in results) + "\n", encoding="utf-8")
    ok = sum(r["status"] in ("ok", "cached") for r in results)
    return {"total": len(results), "fetched_or_cached": ok, "failed": len(results) - ok}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="build_known_corpus.py", description=__doc__)
    p.add_argument("--economy", default=None, help="ISO-3 economy filter, e.g. SGP")
    p.add_argument("--browser", action="store_true", help="also use the browser path (JS sites; slower)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--timeout", type=int, default=90, help="per-law fetch timeout (s)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print(f"SENTINEL — building KNOWN corpus from {INVENTORY_CSV.name} …")
    summary = asyncio.run(_build(args))
    print(f"\n{summary['fetched_or_cached']}/{summary['total']} laws in corpus "
          f"({summary['failed']} unreachable). Index: {CORPUS_DIR / 'manifest.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
