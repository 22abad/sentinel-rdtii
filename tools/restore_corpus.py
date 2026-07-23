#!/usr/bin/env python3
"""Detect and restore corrupted Round-2 corpus texts.

The manifest (``data/round2_corpus/manifest.jsonl``) records, for every fetched
law, the ``char_count`` and ``sha256`` of the text that was originally fetched.
A later backfill (``fill_corpus.py``) can mis-match a search result and OVERWRITE
a law's ``.txt`` with the wrong (usually much shorter) document — silently
poisoning the offline corpus. Symptom: ``run_corpus`` produces 0 rows for a
pillar because the on-disk text is a different law with no relevant provisions.

This tool is the integrity guard + repair:

    python tools/restore_corpus.py --economy IDN --check     # audit only
    python tools/restore_corpus.py --economy IDN             # audit + re-fetch

A file is CORRUPT when its on-disk sha256 differs from the manifest sha256 AND
its size is materially smaller than the recorded ``char_count`` (a mis-fill
truncates). Each corrupt file is re-fetched from the manifest's ``url_used``
(the URL that produced the good text) and accepted only when the re-fetched
text matches the recorded ``char_count`` (exact) or the recorded ``sha256``.
Nothing is fabricated: a law that can't be re-fetched cleanly is left flagged,
never patched with wrong text (CLAUDE.md rule 5).
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

MANIFEST = REPO_ROOT / "data" / "round2_corpus" / "manifest.jsonl"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _load_manifest() -> list[dict]:
    recs: list[dict] = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.strip():
            recs.append(json.loads(line))
    return recs


def judge_integrity(
    disk: str | None, want_hash: str, want_cc: int
) -> tuple[bool, str]:
    """Pure integrity verdict for one corpus text against its manifest baseline.

    (corrupt, reason). A file is corrupt when it is missing, or its sha256
    differs from the recorded good hash AND it is truncated to < 50% of the
    recorded char_count (the mis-fill failure mode). A changed-but-comparable
    file is NOT flagged (could be a legitimate re-fetch drift)."""
    if disk is None:
        return True, "missing on disk"
    if want_hash and _sha(disk) == want_hash:
        return False, "sha256 match"
    if want_cc and len(disk) < want_cc * 0.5:
        return True, f"truncated: disk {len(disk)} << manifest {want_cc}"
    if not want_hash and not want_cc:
        return False, "no baseline to check"
    return False, f"changed but comparable size (disk {len(disk)} vs {want_cc})"


def _is_corrupt(rec: dict) -> tuple[bool, str]:
    """Return (corrupt, reason). Only judges records that claim to have text."""
    if rec.get("status") not in ("ok", "cached"):
        return False, "not-ok"
    path = REPO_ROOT / rec.get("text_path", "")
    disk = path.read_text(encoding="utf-8") if path.exists() else None
    return judge_integrity(disk, rec.get("sha256", ""), int(rec.get("char_count") or 0))


async def _refetch(rec: dict, timeout: int) -> tuple[str, str] | None:
    """Re-fetch a law's text from its recorded good URL. Returns (text, url) or
    None. Accepts only text whose length or sha256 matches the manifest."""
    from services.document_fetch import fetch_document_text

    urls = [rec.get("url_used")] if rec.get("url_used") else []
    urls += [u for u in (rec.get("urls") or []) if u not in urls]
    want_hash = rec.get("sha256", "")
    want_cc = int(rec.get("char_count") or 0)
    for url in urls:
        if not url:
            continue
        try:
            doc = await asyncio.wait_for(
                fetch_document_text(url, browser_mode="http"), timeout=timeout
            )
        except Exception:  # noqa: BLE001 — try the next URL
            continue
        text = getattr(doc, "text", "") or ""
        if not text:
            continue
        # Accept the re-fetch when it is the good full text. An exact sha256 /
        # char_count match is ideal, but a bpk Details page renders at a
        # slightly different length each visit, so also accept any fetch from
        # the recorded good URL that is NOT truncated (>= 70% of the original
        # char_count). The corruption we are repairing is always < 50% of
        # char_count, so this still cannot re-accept a truncated mis-fill.
        good = (
            (want_hash and _sha(text) == want_hash)
            or (want_cc and abs(len(text) - want_cc) <= max(50, want_cc * 0.02))
            or (want_cc and len(text) >= want_cc * 0.7)
        )
        if good:
            return text, url
    return None


_ARTICLE_RE = re.compile(
    r"\b[Aa]rticle\s+\d+|\b[Ss]ection\s+\d+|第[一二三四五六七八九十百千]+条"
    r"|Стать[яи]\s+\d+|Пункт\s+\d+|มาตรา\s*\d+"
    # Indonesian/Malay 'Pasal', Lao 'ມາດຕາ', Mongolian 'зүйл' article markers —
    # without these the classifier mislabels real non-English statutes (71 of
    # Indonesia's 'Pasal' statutes) as summaries.
    r"|\bPasal\s+\d+|ມາດຕາ\s*\d+|\d+\s*дугаар\s+зүйл|\bзүйл\b",
)
_SUMMARY_RE = re.compile(
    r"will\s+establish|has\s+passed|passed\s+the\s+law|law\s+firm|this\s+article"
    r"|in\s+summary|overview\s+of|is\s+expected\s+to|the\s+government\s+has"
    r"|client\s+alert|legal\s+update|newsletter",
    re.IGNORECASE,
)


def classify_text_quality(text: str) -> tuple[str, str]:
    """Is a corpus text the PRIMARY STATUTE, or a summary/stub that carries no
    verbatim provisions? Extraction can only quote statutory text — a law-firm
    summary or a fetch stub yields nothing, which reads as an extraction miss
    but is really a corpus-quality gap. Heuristic, deliberately conservative.

    Returns (kind, detail): STATUTE | SUMMARY | STUB | THIN.
    """
    t = text or ""
    if len(t) < 3000:
        return "STUB", f"only {len(t)} chars — not a full statute"
    arts = len(_ARTICLE_RE.findall(t))
    if arts >= 5:
        return "STATUTE", f"{arts} article/section markers"
    if _SUMMARY_RE.search(t) or arts < 2:
        return "SUMMARY", f"{arts} article markers, summary/prose language"
    return "THIN", f"only {arts} article markers"


def _quality_audit(recs: list[dict]) -> int:
    from collections import Counter

    kinds: Counter[str] = Counter()
    flagged: list[tuple[str, str, str]] = []
    for r in recs:
        if r.get("status") not in ("ok", "cached"):
            continue
        path = REPO_ROOT / r.get("text_path", "")
        if not path.exists():
            continue
        kind, detail = classify_text_quality(path.read_text(encoding="utf-8"))
        kinds[kind] += 1
        if kind != "STATUTE":
            flagged.append((r.get("economy", ""), r.get("law_name", "")[:46], f"{kind}: {detail}"))
    print(f"corpus text quality over {sum(kinds.values())} texts: {dict(kinds)}")
    print(f"non-statute (summary/stub/thin) texts a judge can't extract from: {len(flagged)}")
    for econ, name, why in flagged:
        print(f"  {econ} | {name:46} | {why}")
    return 0


async def _run(args: argparse.Namespace) -> int:
    recs = _load_manifest()
    if args.economy:
        recs = [r for r in recs if r.get("economy") == args.economy.upper()]
    if args.quality:
        return _quality_audit(recs)
    corrupt = [(r, why) for r in recs for ok, why in [_is_corrupt(r)] if ok]
    print(f"scanned {len(recs)} record(s); {len(corrupt)} corrupt")
    for r, why in corrupt:
        print(f"  CORRUPT {r.get('economy')} | {r.get('law_name','')[:50]} | {why}")
    if args.check or not corrupt:
        return 0

    print(f"\nre-fetching {len(corrupt)} law(s)…")
    fixed = 0
    still_bad: list[str] = []
    for r, _why in corrupt:
        res = await _refetch(r, args.timeout)
        name = f"{r.get('economy')} {r.get('law_name','')[:45]}"
        if res is None:
            still_bad.append(name)
            print(f"  FAIL {name} — no URL yielded matching text")
            continue
        text, used = res
        path = REPO_ROOT / r["text_path"]
        path.write_text(text, encoding="utf-8")
        fixed += 1
        print(f"  OK   {name} ({len(text)//1000}k) via {used[:60]}")
    print(f"\nrestored {fixed}/{len(corrupt)}; {len(still_bad)} still flagged")
    for n in still_bad:
        print(f"  STILL BAD: {n}")
    return 0 if not still_bad else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="restore_corpus.py", description=__doc__)
    p.add_argument("--economy", default=None, help="ISO-3 filter, e.g. IDN")
    p.add_argument("--check", action="store_true", help="audit only, do not fetch")
    p.add_argument("--quality", action="store_true",
                   help="audit text QUALITY (statute vs summary/stub), do not fetch")
    p.add_argument("--timeout", type=int, default=90, help="per-URL fetch timeout (s)")
    args = p.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
