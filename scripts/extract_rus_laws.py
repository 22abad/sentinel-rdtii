#!/usr/bin/env python3
"""Extract specific Russian federal laws from RusLawOD (Hugging Face streaming).
Filters by doc number + date year + keyword in heading to avoid same-number collisions."""
import os, hashlib, json

CORPUS = "/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private/data/round2_corpus/RUS"
MANIFEST = "/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private/data/round2_corpus/manifest.jsonl"
os.makedirs(CORPUS, exist_ok=True)

# (docNumber, year, keyword-in-heading) → RDTII indicator
TARGETS = [
    ("152-ФЗ", "2006", "персональных данных", "6.3",
     "Federal Law No. 152-FZ On Personal Data"),
    ("374-ФЗ", "2016", "противодействии терроризму", "4.9",
     "Federal Law No. 374-FZ On Counterterrorism Amendments (Yarovaya)"),
    ("149-ФЗ", "2006", "информации, информационных технологий", "8.2",
     "Federal Law No. 149-FZ On Information, Information Technologies and Protection of Information"),
]

try:
    from datasets import load_dataset
except ImportError:
    print("pip install datasets first")
    raise SystemExit(1)

print("Loading RusLawOD (streaming)...")
ds = load_dataset("irlspbru/RusLawOD", split="train", streaming=True)

found_en = {}  # english_name → indicator
count = 0
for row in ds:
    count += 1
    num = row.get("docNumberIPS", "") or ""
    date_str = row.get("docdateIPS", "") or ""
    heading = row.get("headingIPS", "") or ""
    year = date_str[:4] if date_str else ""

    for target_num, target_year, keyword, indicator, en_name in TARGETS:
        if en_name in found_en:
            continue
        if num == target_num and year == target_year and keyword.lower() in heading.lower():
            text = row.get("textIPS", "") or ""
            doc_type = row.get("doc_typeIPS", "") or ""

            full_text = f"{en_name}\n{heading}\nType: {doc_type}\nDate: {date_str}\n\n{text}"

            slug = f"federal-law-{target_num.lower()}-{target_year}"
            slug = slug.replace("ё","e").replace("фз","fz").replace("-","")
            fname = f"{slug}.txt"
            fpath = os.path.join(CORPUS, fname)

            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(full_text)

            sha = hashlib.sha256(full_text.encode()).hexdigest()
            chars = len(full_text)

            print(f"✓ {target_num} ({target_year}) → RUS {indicator}")
            print(f"  {en_name}: {chars} chars, sha={sha[:16]}...")

            # Update manifest
            entries = [json.loads(l) for l in open(MANIFEST) if l.strip()]
            entries = [e for e in entries if not (e.get('economy') == 'RUS' and e.get('indicator_id') == indicator)]
            entries.append({
                "economy": "RUS",
                "law_name": en_name,
                "indicator_id": indicator,
                "urls": [f"https://huggingface.co/datasets/irlspbru/RusLawOD (doc {target_num}, {target_year})"],
                "text_path": f"data/round2_corpus/RUS/{fname}",
                "status": "ok",
                "char_count": chars,
                "sha256": sha
            })
            with open(MANIFEST, 'w', encoding='utf-8') as f:
                for e in entries:
                    f.write(json.dumps(e, ensure_ascii=False) + '\n')

            found_en[en_name] = indicator
            break

    if len(found_en) == len(TARGETS):
        break
    if count % 100000 == 0:
        print(f"  scanned {count} rows, found {len(found_en)}/3...")

print(f"\nScanned {count} rows, found {len(found_en)}/3 laws")
for name, ind in found_en.items():
    print(f"  {name} → RUS {ind}")

if len(found_en) < 3:
    print("\nMissing laws — dumping sample rows for debugging:")
    ds2 = load_dataset("irlspbru/RusLawOD", split="train", streaming=True)
    samples = {"152-ФЗ": 0, "374-ФЗ": 0, "149-ФЗ": 0}
    for row in ds2:
        num = row.get("docNumberIPS", "") or ""
        if num in samples and samples[num] < 3:
            heading = row.get("headingIPS", "") or ""
            date_str = row.get("docdateIPS", "") or ""
            print(f"  {num} date={date_str} heading={heading[:120]}")
            samples[num] += 1
            if all(v >= 3 for v in samples.values()):
                break
