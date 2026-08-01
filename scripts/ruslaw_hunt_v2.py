#!/usr/bin/env python3
"""Stream RusLawOD, stop after finding 3 target laws.
Uses datasets streaming to avoid 6GB download."""
import os, hashlib, json, sys

MANIFEST = "/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private/data/round2_corpus/manifest.jsonl"
CORPUS = "/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private/data/round2_corpus/RUS"
os.makedirs(CORPUS, exist_ok=True)

try:
    from datasets import load_dataset
except ImportError:
    print("pip install datasets"); sys.exit(1)

# (docNumber, year, keyword, indicator, en_name)
TARGETS = [
    ("152-ФЗ", "2006", "персональных данных", "6.3", "Federal Law No. 152-FZ On Personal Data"),
    ("374-ФЗ", "2016", "противодействии терроризму", "4.9", "Federal Law No. 374-FZ Yarovaya Law"),
]

print("Loading RusLawOD (streaming, no download)...")
ds = load_dataset("irlspbru/RusLawOD", split="train", streaming=True)

found_indicators = set()
count = 0
for row in ds:
    count += 1
    num = (row.get("docNumberIPS") or "").strip()
    date_str = (row.get("docdateIPS") or "").strip()
    year = date_str[-4:] if len(date_str) >= 4 else ""
    heading = (row.get("headingIPS") or "").strip().lower()

    for tnum, tyear, tkw, indicator, ename in TARGETS:
        if indicator in found_indicators:
            continue
        if num == tnum and year == tyear and tkw.lower() in heading:
            text = row.get("textIPS") or ""
            doc_type = row.get("doc_typeIPS") or ""

            full = f"{ename}\n{row.get('headingIPS','')}\nType: {doc_type}\nDate: {date_str}\n\n{text}"
            slug = f"federal-law-{tnum.lower().replace('ё','e').replace('фз','fz').replace('-','')}-{tyear}"
            fpath = os.path.join(CORPUS, f"{slug}.txt")

            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(full)

            sha = hashlib.sha256(full.encode()).hexdigest()
            chars = len(full)
            print(f"✓ {tnum} ({tyear}) → RUS {indicator}: {chars} chars")

            entries = [json.loads(l) for l in open(MANIFEST) if l.strip()]
            entries = [e for e in entries if not (e.get('economy')=='RUS' and e.get('indicator_id')==indicator)]
            entries.append({
                "economy": "RUS", "law_name": ename, "indicator_id": indicator,
                "urls": [f"https://huggingface.co/datasets/irlspbru/RusLawOD ({tnum}, {tyear})"],
                "text_path": f"data/round2_corpus/RUS/{slug}.txt",
                "status": "ok", "char_count": chars, "sha256": sha
            })
            with open(MANIFEST, 'w') as f:
                for e in entries: f.write(json.dumps(e, ensure_ascii=False)+'\n')

            found_indicators.add(indicator)
            break

    if len(found_indicators) == len(TARGETS):
        break
    if count % 100000 == 0:
        print(f"  scanned {count} rows, found {len(found_indicators)}/2...")
    if count > 300000:
        print(f"  stopped at 300K rows")
        break

print(f"\nScanned {count} rows, found {len(found_indicators)}/{len(TARGETS)}")
if found_indicators:
    print("Manifest updated!")
else:
    print("NOT FOUND — sampling 3 rows to debug:")
    ds2 = load_dataset("irlspbru/RusLawOD", split="train", streaming=True)
    for i, r in enumerate(ds2):
        if i >= 3: break
        num = r.get("docNumberIPS","") or ""
        date = r.get("docdateIPS","") or ""
        hdr = (r.get("headingIPS","") or "")[:80]
        print(f"  row {i}: num='{num}' date='{date}' heading='{hdr}'")
