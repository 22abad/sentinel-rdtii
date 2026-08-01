#!/usr/bin/env python3
"""Extract more RUS laws: Presidential Decree 215, EAEU Treaty, etc."""
import os, hashlib, json
from datasets import load_dataset

MANIFEST = "/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private/data/round2_corpus/manifest.jsonl"
CORPUS = "/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private/data/round2_corpus/RUS"
os.makedirs(CORPUS, exist_ok=True)

# (keyword-in-heading, year-hint, indicator, en_name)
TARGETS = [
    ("структуре федеральных органов исполнительной власти", "2018", "5.7",
     "Presidential Decree No. 215 On the Structure of Federal Executive Authorities"),
    ("О персональных данных", "2006", "6.3",
     "Federal Law No. 152-FZ On Personal Data"),  # re-extract for quality
]

print("Scanning RusLawOD for RUS 5.7 + 6.3...")
ds = load_dataset("irlspbru/RusLawOD", split="train", streaming=True)

found = set()
for row in ds:
    hdr = (row.get("headingIPS") or "").lower()
    num = row.get("docNumberIPS") or ""
    date = (row.get("docdateIPS") or "")
    year = date[-4:] if len(date) >= 4 else ""

    for kw, target_year, indicator, ename in TARGETS:
        if indicator in found:
            continue
        if kw.lower() in hdr and year == target_year:
            text = row.get("textIPS") or ""
            dt = row.get("doc_typeIPS") or ""
            full = f"{ename}\n{row.get('headingIPS','')}\nType: {dt}\nDate: {date}\n\n{text}"
            slug = f"rus-{indicator.replace('.','-')}.txt"
            fpath = os.path.join(CORPUS, slug)

            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(full)
            sha = hashlib.sha256(full.encode()).hexdigest()
            print(f"✓ {ename[:60]} ({year}) → RUS {indicator}: {len(full)} chars")

            entries = [json.loads(l) for l in open(MANIFEST) if l.strip()]
            entries = [e for e in entries if not (e.get('economy')=='RUS' and e.get('indicator_id')==indicator)]
            entries.append({
                "economy": "RUS", "law_name": ename, "indicator_id": indicator,
                "urls": [f"https://huggingface.co/datasets/irlspbru/RusLawOD ({num}, {year})"],
                "text_path": f"data/round2_corpus/RUS/{slug}",
                "status": "ok", "char_count": len(full), "sha256": sha
            })
            with open(MANIFEST, 'w') as f:
                for e in entries: f.write(json.dumps(e, ensure_ascii=False)+'\n')
            found.add(indicator)
            break
    if len(found) == len(TARGETS):
        break

print(f"Found {len(found)}/{len(TARGETS)}")
