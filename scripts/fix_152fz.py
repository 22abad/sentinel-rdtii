#!/usr/bin/env python3
"""Fix 152-FZ: remove 760-char bad entry, re-extract full 47K text."""
import json, hashlib

MANIFEST = "/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private/data/round2_corpus/manifest.jsonl"

# 1. Remove bad 760-char entry
entries = [json.loads(l) for l in open(MANIFEST) if l.strip()]
entries = [e for e in entries if not (e.get('economy')=='RUS' and e.get('indicator_id')=='6.3' and e.get('char_count', 99999) < 1000)]
print(f"After cleanup: {len(entries)} entries, {sum(1 for e in entries if e.get('economy')=='RUS' and e.get('indicator_id')=='6.3')} RUS 6.3 entries")

# 2. Re-extract from RusLawOD
from datasets import load_dataset
ds = load_dataset("irlspbru/RusLawOD", split="train", streaming=True)
for row in ds:
    hdr = (row.get("headingIPS") or "").lower()
    date = row.get("docdateIPS") or ""
    if "персональных данных" in hdr and date == "27.07.2006":
        text = row.get("textIPS") or ""
        heading = row.get("headingIPS") or ""
        doc_type = row.get("doc_typeIPS") or ""

        full = f"Federal Law No. 152-FZ On Personal Data\n{heading}\nType: {doc_type}\nDate: {date}\n\n{text}"
        path = "data/round2_corpus/RUS/federal-law-152fz-2006.txt"
        with open(path, 'w') as f:
            f.write(full)

        sha = hashlib.sha256(full.encode()).hexdigest()
        print(f"Re-extracted: {len(full)} chars, sha={sha[:16]}...")

        entries.append({
            "economy": "RUS", "law_name": "Federal Law No. 152-FZ On Personal Data",
            "indicator_id": "6.3",
            "urls": ["https://huggingface.co/datasets/irlspbru/RusLawOD (152-ФЗ, 27.07.2006)"],
            "text_path": path, "status": "ok", "char_count": len(full), "sha256": sha
        })

        with open(MANIFEST, 'w') as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + '\n')
        print(f"Manifest: {len(entries)} entries")
        break
