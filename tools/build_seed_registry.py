#!/usr/bin/env python3
"""Merge every known-good official source URL into one seed registry.

The "important URLs" for a run live in two places today:

  * ``data/law_library/manifest.jsonl`` — the curated library: exact official
    URL + SHA-256-verified cached full text (11 laws, pillar-tagged).
  * ``data/known_corpus/manifest.jsonl`` — the broad KNOWN inventory: exact
    official URL + fetch status for ~204 laws.

This tool folds both into a single, de-duplicated, tiered source of truth at
``data/seed_sources.jsonl`` so the seed-first retrieval path (and any judge who
wants to eyeball "which URLs do we trust") has one auditable list.

Tiers (most reliable first):

  1. ``library_cached``  — in the law library with verified cached text; the
     seed-first run serves these OFFLINE before touching the network.
  2. ``corpus_ok``       — official URL whose full text fetched cleanly into the
     local corpus (available to fetch directly, skipping blind search).
  3. ``corpus_failed``   — a known official URL that did not fetch (dead link /
     JS-only portal / not a single-statute page); recorded, not hidden.

Usage:
    python tools/build_seed_registry.py            # write data/seed_sources.jsonl
    python tools/build_seed_registry.py --check    # verify it is up to date (CI)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SERVICE = REPO_ROOT / "ai-service"
if str(AI_SERVICE) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE))

from discovery.metadata import canonicalize_url  # noqa: E402

LIBRARY_MANIFEST = REPO_ROOT / "data" / "law_library" / "manifest.jsonl"
CORPUS_MANIFEST = REPO_ROOT / "data" / "known_corpus" / "manifest.jsonl"
SEED_REGISTRY = REPO_ROOT / "data" / "seed_sources.jsonl"

_TIER_RANK = {"library_cached": 0, "corpus_ok": 1, "corpus_failed": 2}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_rows() -> list[dict]:
    """Merge the two manifests into deduped, tiered seed rows."""

    by_url: dict[str, dict] = {}

    def _offer(row: dict) -> None:
        key = canonicalize_url(row["url"])
        existing = by_url.get(key)
        # Keep the most reliable tier when the same URL appears twice.
        if existing is None or _TIER_RANK[row["tier"]] < _TIER_RANK[existing["tier"]]:
            by_url[key] = row

    # Layer 1 — the curated library (cached, pillar-tagged, most reliable).
    for e in _read_jsonl(LIBRARY_MANIFEST):
        _offer({
            "economy": e["economy"],
            "law_name": e["law_name"],
            "url": e["official_url"],
            "tier": "library_cached",
            "pillars": e.get("pillars", []),
            "discovery_tag": e.get("discovery_tag", "KNOWN"),
            "sha256": e.get("sha256", ""),
            "text_path": e.get("text_path", ""),
        })

    # Layer 2 — the broad corpus (URL + fetch status, no pillar tags).
    for e in _read_jsonl(CORPUS_MANIFEST):
        ok = e.get("status") in ("ok", "cached")
        _offer({
            "economy": e["economy"],
            "law_name": e["law_name"],
            "url": e["url"],
            "tier": "corpus_ok" if ok else "corpus_failed",
            "pillars": [],
            "discovery_tag": "KNOWN",
            "sha256": e.get("sha256", ""),
            "text_path": e.get("text_path", "") if ok else "",
        })

    return sorted(
        by_url.values(),
        key=lambda r: (_TIER_RANK[r["tier"]], r["economy"], r["law_name"].lower()),
    )


def render(rows: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="build_seed_registry.py", description=__doc__)
    p.add_argument("--check", action="store_true", help="fail if the on-disk registry is stale")
    args = p.parse_args(argv)

    rows = build_rows()
    content = render(rows)

    if args.check:
        current = SEED_REGISTRY.read_text(encoding="utf-8") if SEED_REGISTRY.exists() else ""
        if current != content:
            print("seed registry is stale — run: python tools/build_seed_registry.py", file=sys.stderr)
            return 1
        print(f"seed registry up to date ({len(rows)} sources).")
        return 0

    SEED_REGISTRY.write_text(content, encoding="utf-8")
    tiers = {t: sum(r["tier"] == t for r in rows) for t in _TIER_RANK}
    print(f"Wrote {len(rows)} seed sources to {SEED_REGISTRY.relative_to(REPO_ROOT)}")
    print(f"  library_cached={tiers['library_cached']}  "
          f"corpus_ok={tiers['corpus_ok']}  corpus_failed={tiers['corpus_failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
