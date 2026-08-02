#!/usr/bin/env python3
"""Scan RusLawOD parquet files for our target laws.
Downloads only file metadata first, then the smallest matching file."""
import requests, io, os, hashlib, json

CORPUS = "/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private/data/round2_corpus/RUS"
MANIFEST = "/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private/data/round2_corpus/manifest.jsonl"
os.makedirs(CORPUS, exist_ok=True)

TARGETS = [
    ("152-ФЗ", "2006", "персональных", "6.3", "Federal Law No. 152-FZ On Personal Data"),
    ("374-ФЗ", "2016", "терроризм", "4.9", "Federal Law No. 374-FZ (Yarovaya)"),
    ("149-ФЗ", "2006", "информационных технологий", "8.2", "Federal Law No. 149-FZ On Information"),
]

BASE = "https://huggingface.co/datasets/irlspbru/RusLawOD/resolve/main"
FILES = [f"ruslawod_{i:02d}.parquet" for i in range(1, 11)]

print(f"Downloading parquet files one by one, scanning for {len(TARGETS)} laws...")

try:
    import pyarrow.parquet as pq
except ImportError:
    print("pip install pyarrow")
    raise SystemExit(1)

found = {}
for fname in FILES:
    url = f"{BASE}/{fname}"
    print(f"\nFetching {fname}...")
    resp = requests.get(url, stream=True, timeout=120)
    # Read in chunks, but pyarrow needs the full file for metadata
    # So we download it all - these are ~600MB each
    data = io.BytesIO(resp.content)
    print(f"  Downloaded {len(resp.content)/1024/1024:.0f}MB, scanning...")

    table = pq.read_table(data, columns=["docNumberIPS", "docdateIPS", "headingIPS", "textIPS", "doc_typeIPS"])
    df = table.to_pandas()
    print(f"  {len(df)} rows")

    for _, row in df.iterrows():
        num = str(row.get("docNumberIPS", "")) or ""
        date_str = str(row.get("docdateIPS", "")) or ""
        heading = str(row.get("headingIPS", "")) or ""
        year = date_str[:4] if date_str else ""

        for target_num, target_year, keyword, indicator, en_name in TARGETS:
            if en_name in found:
                continue
            if num == target_num and year == target_year and keyword.lower() in heading.lower():
                text = str(row.get("textIPS", "")) or ""
                doc_type = str(row.get("doc_typeIPS", "")) or ""

                full_text = f"{en_name}\n{heading}\nType: {doc_type}\nDate: {date_str}\n\n{text}"
                slug = f"federal-law-{target_num.lower().replace('ё','e')}-{target_year}"
                slug = slug.replace("фз","fz").replace("-","")
                fpath = os.path.join(CORPUS, f"{slug}.txt")

                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write(full_text)

                sha = hashlib.sha256(full_text.encode()).hexdigest()
                chars = len(full_text)
                print(f"\n✓ FOUND {target_num} ({year}) → RUS {indicator} in {fname}!")
                print(f"  {en_name}: {chars} chars, saving...")

                # Update manifest
                entries = [json.loads(l) for l in open(MANIFEST) if l.strip()]
                entries = [e for e in entries if not (e.get('economy') == 'RUS' and e.get('indicator_id') == indicator)]
                entries.append({
                    "economy": "RUS",
                    "law_name": en_name,
                    "indicator_id": indicator,
                    "urls": [f"https://huggingface.co/datasets/irlspbru/RusLawOD ({target_num}, {target_year})"],
                    "text_path": f"data/round2_corpus/RUS/{slug}.txt",
                    "status": "ok",
                    "char_count": chars,
                    "sha256": sha
                })
                with open(MANIFEST, 'w', encoding='utf-8') as f:
                    for e in entries:
                        f.write(json.dumps(e, ensure_ascii=False) + '\n')

                found[en_name] = indicator

    if len(found) == len(TARGETS):
        print(f"\nAll {len(TARGETS)} laws found!")
        break

    # Don't download all 10 files - stop early if we have enough
    if len(found) >= 2:
        print(f"  Found {len(found)} so far, continuing...")

print(f"\nTotal found: {len(found)}/{len(TARGETS)}")
for name, ind in found.items():
    print(f"  {name} → RUS {ind}")
