"""Fill missing corpus laws for any R2 economy via its discovery adapter.

Many baseline laws have no local text because their original reference URLs
rotted. Each economy's discovery adapter finds the CURRENT official document by
the portal's own search, sidestepping the dead links. Usage:

    python tools/fill_corpus.py --economy IND    # india_code
    python tools/fill_corpus.py --economy IDN    # indonesia_bpk
    python tools/fill_corpus.py --economy THA     # mekong_ckan
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ai-service"))

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "data" / "round2_corpus"
MANIFEST = CORPUS / "manifest.jsonl"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:80]


def _clean_query(law_name: str) -> str:
    """Reduce a noisy baseline law name to a clean India Code search query."""
    # Keep text up to the first ';' or newline (drop the ministry tail).
    core = re.split(r"[;\n]", law_name)[0]
    core = re.sub(r"\bNo\.?\s*\d+\b", "", core)  # drop "No.18"
    core = re.sub(r"\bGovernment of India\b.*", "", core, flags=re.I)
    return re.sub(r"\s+", " ", core).strip()


_ADAPTERS = {"IND": ("india_code", "https://www.indiacode.nic.in", ["indiacode.nic.in", "www.indiacode.nic.in"]),
             "IDN": ("indonesia_bpk", "https://peraturan.bpk.go.id", ["peraturan.bpk.go.id"]),
             "THA": ("mekong_ckan", "https://data.opendevelopmentmekong.net", ["data.opendevelopmentmekong.net"]),
             "LAO": ("mekong_ckan", "https://data.opendevelopmentmekong.net", ["data.opendevelopmentmekong.net"])}


async def main(economy: str) -> None:
    from discovery.adapters import get_adapter
    from discovery.schemas import LegalSourceConfig
    from crawler import fetch_legal_content
    if economy not in _ADAPTERS:
        print(f"No backfill adapter for {economy}; supported: {list(_ADAPTERS)}"); return
    adapter_name, base_url, domains = _ADAPTERS[economy]

    inv = [json.loads(l) for l in open(REPO / "data/round2_inventory.jsonl") if l.strip()]
    cached = set()
    for line in open(MANIFEST):
        d = json.loads(line)
        # A law is already present if it was fetched by build_round2_corpus
        # (status "ok") OR a prior backfill ("cached"). Treating only "cached"
        # as present made this tool re-fetch every original law and OVERWRITE
        # its good text with a (frequently wrong) bpk search result — the
        # 34-file IDN corpus corruption. See tools/restore_corpus.py.
        if d.get("economy") == economy and d.get("status") in ("ok", "cached"):
            cached.add(d.get("law_name", ""))

    eco = [r for r in inv if r.get("economy") == economy]
    missing_acts = []
    seen_q = set()
    for r in eco:
        name = r.get("law_name", "")
        if name in cached:
            continue
        if economy == "IND" and ("act" not in name.lower() or "ministry" in name.lower()[:25]):
            continue
        q = _clean_query(name)
        if not q or q.lower() in seen_q:
            continue
        seen_q.add(q.lower())
        missing_acts.append((name, q))

    print(f"Distinct missing {economy} laws to fill: {len(missing_acts)}")
    ad = get_adapter(adapter_name)
    src = LegalSourceConfig(name=adapter_name, base_url=base_url, domains=domains, adapter=adapter_name)
    (CORPUS / economy).mkdir(parents=True, exist_ok=True)
    filled = 0
    def _best_hit(target: str, hits):
        """Pick the hit whose title best matches the target law, not just the
        top search result (India Code ranked a Telangana state Act above the
        central Companies Act). Score by statute number match + word overlap."""
        from submission.novelty import law_number_key
        tk = law_number_key(target)
        tw = {w for w in re.sub(r"[^a-z0-9 ]", " ", target.lower()).split() if len(w) > 3}
        best, best_score = None, -1.0
        for h in hits:
            title = (h.title or "").lower()
            hw = {w for w in re.sub(r"[^a-z0-9 ]", " ", title).split() if len(w) > 3}
            overlap = len(tw & hw) / max(len(tw), 1)
            num_bonus = 1.0 if tk and law_number_key(h.title or "") == tk else 0.0
            # Penalize obvious wrong-jurisdiction state Acts for a central law.
            state_pen = 0.3 if any(s in title for s in ("telangana", "state ", "provincial")) and "state" not in target.lower() else 0.0
            score = overlap + num_bonus - state_pen
            if score > best_score:
                best, best_score = h, score
        # Require a strong match: an exact statute-number match, or the target's
        # distinctive words are mostly present. A weak partial match (e.g. only
        # the word "Act" overlaps) is worse than leaving the law auto-0.
        best_num = law_number_key(best.title or "") if best else None
        strong = best is not None and (
            (tk and best_num == tk) or best_score >= 0.6
        )
        return best if strong else None

    new_rows = []
    for name, q in missing_acts:
        try:
            hits = await ad.search(country_code=economy, source=src, queries=[q], limit=6)
        except Exception as exc:
            print(f"  ✗ {q[:40]}: search {type(exc).__name__}")
            continue
        best = _best_hit(name, hits) if hits else None
        if not best:
            print(f"  ✗ {q[:40]}: no matching hit")
            continue
        hits = [best]
        url = hits[0].url
        try:
            res = await fetch_legal_content(url, timeout=45000)
            text = res.get("text", "") or ""
        except Exception as exc:
            print(f"  ✗ {q[:40]}: fetch {type(exc).__name__}")
            continue
        if len(text) < 1000:
            print(f"  ✗ {q[:40]}: text too short ({len(text)})")
            continue
        path = CORPUS / economy / f"{_slug(name)}.txt"
        # Never shrink a corpus file: if a good text already exists at this slug,
        # a shorter fresh fetch is almost certainly a wrong/partial match — the
        # exact failure mode that poisoned the IDN corpus. Defense in depth on
        # top of the status filter above.
        if path.exists() and path.stat().st_size > len(text.encode()):
            print(f"  ↷ {q[:40]}: keep existing {path.stat().st_size}b > new {len(text.encode())}b")
            continue
        path.write_text(text, encoding="utf-8")
        new_rows.append({
            "economy": economy, "law_name": name,
            "text_path": str(path.relative_to(REPO)),
            "status": "cached", "char_count": len(text),
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "url_used": url, "source": f"{adapter_name}_backfill",
        })
        filled += 1
        print(f"  ✓ {hits[0].title[:44]:44} ({len(text)//1000}k)")

    if new_rows:
        with open(MANIFEST, "a", encoding="utf-8") as f:
            for row in new_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nFilled {filled} / {len(missing_acts)} missing {economy} laws.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--economy", required=True)
    asyncio.run(main(ap.parse_args().economy.upper()))
