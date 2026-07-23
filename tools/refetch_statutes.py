#!/usr/bin/env python3
"""Re-fetch PRIMARY STATUTE text for corpus entries that are summaries/stubs.

The coverage gap is dominated by corpus quality: ~58% of corpus texts are
law-firm summaries, fetch stubs, or thin fragments a run cannot extract a
verbatim provision from (see `restore_corpus.py --quality`). This tool targets
those: for each non-statute law it searches (key-free multi-tier: DDG Lite ->
Bing) for the actual statute, fetches candidates, and REPLACES the corpus text
only when the fetched text is (a) STATUTE-quality per classify_text_quality and
(b) larger than what's on disk. Nothing is fabricated — a law whose primary
text can't be found stays as-is and is reported.

    python tools/refetch_statutes.py --economy IDN --pillars 6,7 --check
    python tools/refetch_statutes.py --economy IDN --pillars 6,7 --limit 10

Prioritizes official non-zero cells (the scorable ones). Key-free; honors
RDTII_HTTP_PROXY if set.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
AI = REPO / "ai-service"
# AI must precede REPO on the path: a `crawler/` package at the repo root would
# otherwise shadow ai-service's crawler.py (which exposes fetch_legal_content).
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(AI) not in sys.path:
    sys.path.insert(0, str(AI))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # this tools/ dir
load_dotenv(REPO / ".env")

from restore_corpus import _load_manifest, classify_text_quality  # noqa: E402

MANIFEST = REPO / "data" / "round2_corpus" / "manifest.jsonl"


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def _official_nonzero() -> dict[tuple[str, str], float]:
    """(economy, law_name) -> best official score across its cells (>0 only)."""
    best: dict[tuple[str, str], float] = {}
    for line in (REPO / "data" / "round2_inventory.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        try:
            sc = float(d.get("official_score") or 0)
        except (TypeError, ValueError):
            sc = 0.0
        if sc <= 0:
            continue
        k = (d.get("economy", ""), d.get("law_name", ""))
        best[k] = max(best.get(k, 0.0), sc)
    return best


def _pillar_of(law_name: str, economy: str) -> set[int]:
    out: set[int] = set()
    for line in (REPO / "data" / "round2_inventory.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("economy") == economy and d.get("law_name") == law_name:
            try:
                out.add(int(d.get("pillar", 0) or 0))
            except (TypeError, ValueError):
                pass
    return out


def _query(law_name: str) -> str:
    # First act in a multi-act cell, trimmed of ministry tails.
    import re

    core = re.split(r"[;\n]", law_name)[0]
    core = re.sub(r"\bGovernment of [^,]+,\s*", "", core, flags=re.I)
    return re.sub(r"\s+", " ", core).strip()[:80]


# The primary statute lives on the economy's own portal (an Indonesian PP is a
# PDF on peraturan.bpk.go.id, an Indian Act a bitstream on indiacode.nic.in) —
# a generic web search returns third-party summaries, not the statute. Route
# through the economy's dedicated adapter first (it yields the Download-PDF /
# bitstream URL), then fall back to multi-tier web search.
_ADAPTERS = {
    "IND": ("india_code", "https://www.indiacode.nic.in", ["indiacode.nic.in", "www.indiacode.nic.in"]),
    "IDN": ("indonesia_bpk", "https://peraturan.bpk.go.id", ["peraturan.bpk.go.id"]),
    "THA": ("mekong_ckan", "https://data.opendevelopmentmekong.net", ["data.opendevelopmentmekong.net"]),
    "LAO": ("mekong_ckan", "https://data.opendevelopmentmekong.net", ["data.opendevelopmentmekong.net"]),
}


async def _search_urls(economy: str, query: str, limit: int) -> list[str]:
    urls: list[str] = []
    spec = _ADAPTERS.get(economy.upper())
    if spec:
        try:
            from discovery.adapters import get_adapter
            from discovery.schemas import LegalSourceConfig

            name, base, domains = spec
            src = LegalSourceConfig(name=name, base_url=base, domains=domains, adapter=name)
            hits = await get_adapter(name).search(
                country_code=economy.upper(), source=src, queries=[query], limit=limit
            )
            urls.extend(h.url for h in hits)
        except Exception:  # noqa: BLE001
            pass
    if len(urls) < 2:  # thin adapter result -> add generic web search
        try:
            from discovery.adapters.search_engine import MultiTierSearchBackend

            hits = await MultiTierSearchBackend().search(query, limit)
            urls.extend(h.url for h in hits)
        except Exception:  # noqa: BLE001
            pass
    # de-dupe, preserve order
    seen: set[str] = set()
    return [u for u in urls if not (u in seen or seen.add(u))]


async def _fetch(url: str, timeout: int) -> str:
    # HTTP-only (no Playwright): lighter and it doesn't crash on a browser-driver
    # hiccup. The impersonated-fetch fallback inside document_fetch still clears
    # Cloudflare-fronted portals via curl_cffi.
    from services.document_fetch import fetch_document_text

    try:
        doc = await asyncio.wait_for(
            fetch_document_text(url, browser_mode="http"), timeout=timeout
        )
        return getattr(doc, "text", "") or ""
    except Exception:  # noqa: BLE001
        return ""


async def _run(args: argparse.Namespace) -> int:
    pillars = {int(p) for p in (args.pillars or "").split(",") if p.strip()} if args.pillars else None
    nonzero = _official_nonzero()

    # Candidate corpus entries: non-statute quality, optionally scoped by
    # economy/pillar, prioritised by official score then how thin they are.
    cands: list[tuple[float, dict, str]] = []
    for r in _load_manifest():
        if r.get("status") not in ("ok", "cached"):
            continue
        econ = r.get("economy", "")
        if args.economy and econ != args.economy.upper():
            continue
        p = REPO / r.get("text_path", "")
        if not p.exists():
            continue
        kind, _ = classify_text_quality(p.read_text(encoding="utf-8"))
        if kind == "STATUTE":
            continue
        name = r.get("law_name", "")
        if pillars is not None and not (_pillar_of(name, econ) & pillars):
            continue
        score = nonzero.get((econ, name), 0.0)
        cands.append((score, r, kind))

    cands.sort(key=lambda t: -t[0])
    if args.limit:
        cands = cands[: args.limit]
    print(f"non-statute corpus texts to repair: {len(cands)}"
          f"{' (official-scored first)' if nonzero else ''}")
    for score, r, kind in cands:
        print(f"  [{kind:7} score {score:>3}] {r.get('economy')} | {r.get('law_name','')[:52]}")
    if args.check or not cands:
        return 0

    new_rows: list[dict] = []
    fixed = 0
    for _score, r, _kind in cands:
        econ, name = r.get("economy", ""), r.get("law_name", "")
        path = REPO / r["text_path"]
        cur_len = len(path.read_text(encoding="utf-8"))
        urls = await _search_urls(econ, _query(name), 6)
        got = None
        for url in urls[:5]:
            text = await _fetch(url, args.timeout)
            if len(text) <= cur_len:
                continue
            if classify_text_quality(text)[0] == "STATUTE":
                got = (text, url)
                break
        label = f"{econ} {name[:42]}"
        if not got:
            print(f"  ✗ {label} — no statute-quality source found ({len(urls)} urls)")
            continue
        text, url = got
        path.write_text(text, encoding="utf-8")
        new_rows.append({
            "economy": econ, "law_name": name,
            "text_path": str(path.relative_to(REPO)), "status": "cached",
            "char_count": len(text), "sha256": _sha(text),
            "url_used": url, "source": "statute_refetch",
        })
        fixed += 1
        print(f"  ✓ {label} — {cur_len}->{len(text)} chars STATUTE via {url[:52]}")

    if new_rows:
        with open(MANIFEST, "a", encoding="utf-8") as f:
            for row in new_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nrepaired {fixed}/{len(cands)} non-statute texts to primary statute")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="refetch_statutes.py", description=__doc__)
    p.add_argument("--economy", default=None, help="ISO-3 filter, e.g. IDN")
    p.add_argument("--pillars", default=None, help="comma list, e.g. 6,7")
    p.add_argument("--limit", type=int, default=None, help="cap laws attempted")
    p.add_argument("--check", action="store_true", help="list targets, don't fetch")
    p.add_argument("--timeout", type=int, default=60, help="per-URL fetch timeout (s)")
    return asyncio.run(_run(p.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
