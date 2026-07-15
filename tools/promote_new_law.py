#!/usr/bin/env python3
"""Promote a verified NEW discovery into the reusable law library.

Once a NEW law found by the discovery sweep has been checked, bank it here so
every FUTURE formal run (`python main.py --economy X --pillar 6,7`) serves it
from the cache and tags it NEW automatically — no re-discovery, deterministic.

    python tools/promote_new_law.py \
        --economy Australia \
        --law-name "Identity Verification Services Act 2023" \
        --url "https://www.legislation.gov.au/C2023A00115/latest/text" \
        --pillars 7 --indicators 7.5 \
        --text-file /path/to/ivs_act_provision.txt \
        --notes "Verified via Federal Register API; pending legal review."

Writes the text under data/law_library/text/, computes its SHA-256, and appends
a manifest row with origin=discovered / discovery_tag=NEW. load_library()
re-checks the hash on every load, so a corrupted cache fails loudly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SERVICE = REPO_ROOT / "ai-service"
if str(AI_SERVICE) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE))

MANIFEST = REPO_ROOT / "data" / "law_library" / "manifest.jsonl"
TEXT_DIR = REPO_ROOT / "data" / "law_library" / "text"

_MANIFEST_ORDER = [
    "law_id", "economy", "law_name", "official_url", "source_status", "pillars",
    "indicator_hints", "language_codes", "text_path", "sha256", "retrieved_at",
    "discovery_tag", "origin", "version", "currency_source", "currency_checked_at",
    "notes",
]


def _slug(economy: str, law_name: str) -> str:
    base = f"{economy}-{law_name}".lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", base)).strip("-")[:80]


def _existing_law_ids() -> set[str]:
    if not MANIFEST.exists():
        return set()
    ids = set()
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            ids.add(json.loads(line)["law_id"])
    return ids


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="promote_new_law.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--economy", required=True, help="Economy name or ISO-3 code")
    p.add_argument("--law-name", required=True)
    p.add_argument("--url", required=True, help="Official source URL")
    p.add_argument("--pillars", required=True, help="Comma list, e.g. 6 or 6,7")
    p.add_argument("--indicators", required=True, help="Comma list, e.g. 7.5 or 6.4,7.1")
    p.add_argument("--text-file", required=True, help="Path to the verified verbatim provision text")
    p.add_argument("--law-id", default=None, help="Override the auto-generated law_id slug")
    p.add_argument("--version", default="", help="Version/compilation string")
    p.add_argument("--language", default="en")
    p.add_argument("--notes", default="")
    p.add_argument("--dry-run", action="store_true", help="Show the entry, don't write")
    return p.parse_args(argv)


def main(argv=None) -> int:
    from law_library import load_library
    from submission.schema import economy_code

    args = parse_args(argv)
    code = economy_code(args.economy)  # validates + normalizes
    text = Path(args.text_file).read_text(encoding="utf-8")
    if len(text.strip()) < 40:
        print("Error: provision text is too short to be a real provision.", file=sys.stderr)
        return 2

    law_id = args.law_id or _slug(code, args.law_name)
    if law_id in _existing_law_ids():
        print(f"Error: law_id '{law_id}' is already in the library (use --law-id to disambiguate).",
              file=sys.stderr)
        return 2

    text_path = TEXT_DIR / f"{law_id}.txt"
    sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    today = date.today().isoformat()
    entry = {
        "law_id": law_id,
        "economy": code,
        "law_name": args.law_name,
        "official_url": args.url,
        "source_status": "in_force",
        "pillars": [int(p) for p in args.pillars.split(",") if p.strip()],
        "indicator_hints": [i.strip() for i in args.indicators.split(",") if i.strip()],
        "language_codes": [args.language],
        "text_path": str(text_path.relative_to(REPO_ROOT)),
        "sha256": sha256,
        "retrieved_at": today,
        "discovery_tag": "NEW",   # a formal run tags it NEW
        "origin": "discovered",   # ...because it was independently found, not in the baseline
        "version": args.version,
        "currency_source": args.url,
        "currency_checked_at": today,
        "notes": args.notes or "NEW discovery promoted to the library; pending legal review.",
    }
    line = json.dumps({k: entry[k] for k in _MANIFEST_ORDER}, ensure_ascii=False)

    if args.dry_run:
        print("[dry-run] would write text to:", text_path.relative_to(REPO_ROOT))
        print("[dry-run] would append manifest row:\n ", line)
        return 0

    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    text_path.write_text(text, encoding="utf-8")
    with MANIFEST.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")

    # Verify: load_library re-computes and checks the SHA-256 on load.
    entries = [e for e in load_library() if e.law_id == law_id]
    if not entries:
        print("Error: promoted entry did not load back (hash mismatch?).", file=sys.stderr)
        return 2
    print(f"✅ Promoted '{args.law_name}' ({code}) to the library as NEW (law_id={law_id}).")
    print("   Future runs will serve it and tag it NEW:")
    print(f"     python main.py --economy {args.economy} --pillar {args.pillars.replace(',', ',')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
