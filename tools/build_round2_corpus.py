#!/usr/bin/env python3
"""Build a local full-text corpus of the Round 2 baseline laws.

Round 2 spans 7 economies (CHN, IND, IDN, LAO, MNG, RUS, THA) whose official
reference URLs live in ``data/round2_inventory.jsonl`` (extracted from the
official Round 2 database by tools/build_round2_baseline.py). This tool
fetches each law's text via the project's own crawler and stores it locally
as plain text plus an index manifest, so the whole Round 2 corpus is
available offline (seed-first retrieval / RAG input).

    python tools/build_round2_corpus.py                 # fetch all (resumable)
    python tools/build_round2_corpus.py --economy IND   # one economy
    python tools/build_round2_corpus.py --limit 20

Improvement over Round 1's build_known_corpus: an inventory row often carries
several reference URLs; they are tried in order until one yields real text,
so a dead primary link no longer loses the law.

Text lands in data/round2_corpus/<ECON>/<slug>.txt (git-ignored — local use);
the index (urls tried, sha256, char_count, status) is written to
data/round2_corpus/manifest.jsonl. Re-running skips laws already fetched.
"""

from __future__ import annotations

import argparse
import asyncio
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

INVENTORY = REPO_ROOT / "data" / "round2_inventory.jsonl"
CORPUS_DIR = REPO_ROOT / "data" / "round2_corpus"

MIN_TEXT_CHARS = 500  # below this it is a JS shell / placeholder, not law text


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:80]


def _laws_from_inventory(economy: str | None) -> list[dict]:
    """Distinct (economy, law) rows with their candidate URLs, in file order."""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for line in INVENTORY.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if economy and row["economy"] != economy.upper():
            continue
        name = row["law_name"].strip()
        if not name or not row["urls"]:
            continue
        key = (row["economy"], _slug(name))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "economy": row["economy"],
            "law_name": name,
            "indicator_id": row["indicator_id"],
            "urls": row["urls"],
        })
    return out


async def _fetch_first_success(urls: list[str], timeout: int) -> tuple[str, str]:
    """Try each URL in order; return (text, url_used). Raises if all fail."""
    from services.document_fetch import fetch_document_text

    last_error: Exception | None = None
    for url in urls:
        try:
            doc = await asyncio.wait_for(
                fetch_document_text(url, browser_mode="http"), timeout=timeout
            )
            text = getattr(doc, "text", "") or ""
            if len(text) >= MIN_TEXT_CHARS:
                return text, url
            last_error = ValueError(f"too short ({len(text)} chars) — likely a JS shell")
        except Exception as exc:  # noqa: BLE001 — try the next reference URL
            last_error = exc
    raise last_error or ValueError("no URLs to try")


async def _build(args: argparse.Namespace) -> dict:
    laws = _laws_from_inventory(args.economy)
    if args.limit:
        laws = laws[: args.limit]

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
            body, used = await _fetch_first_success(law["urls"], args.timeout)
            text_path.write_text(body, encoding="utf-8")
            row.update(status="ok", url_used=used, char_count=len(body),
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
    p = argparse.ArgumentParser(prog="build_round2_corpus.py", description=__doc__)
    p.add_argument("--economy", default=None, help="ISO-3 economy filter, e.g. IND")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--timeout", type=int, default=60, help="per-URL fetch timeout (s)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = asyncio.run(_build(args))
    print(f"\nDone: {summary['fetched_or_cached']}/{summary['total']} laws local "
          f"({summary['failed']} unreachable). Index: {CORPUS_DIR / 'manifest.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
