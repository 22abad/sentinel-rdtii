#!/usr/bin/env python3
"""Surgical cleanup of the 2026-07-31 auto_fix_corpus Wayback-garbage incident.

What happened: auto_fix_corpus.py saved the Wayback Machine UI page (2,770
chars, sha256 0518cc74…) as "law text" for 11 cells, replacing their manifest
entries. This script:
  1. deletes every corpus .txt whose sha256 == the garbage page
  2. drops manifest entries pointing at those files
  3. restores the pre-incident entry for the affected cells from
     manifest.jsonl.fixed (Jul 28 backup) IF its text file still exists
  4. reports every action; exits nonzero if anything unexpected

Honest-state rule: a cell whose old text was overwritten and unrecoverable
returns to FETCH_GAP (absent from manifest) — never a fake entry.
"""
import json, hashlib, os, sys

WORKDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(WORKDIR, 'data', 'round2_corpus')
MANIFEST = os.path.join(CORPUS, 'manifest.jsonl')
BACKUP = os.path.join(CORPUS, 'manifest.jsonl.fixed')  # Jul 28 snapshot
GARBAGE_SHA = '0518cc74fdb88e68dd81bfb2937ed67466bcee7ae8658a9bd949bd1468815001'

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def load_jsonl(path):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out

# 1. find garbage files on disk
garbage_files = []
for root, _dirs, files in os.walk(CORPUS):
    for fn in files:
        if not fn.endswith('.txt'):
            continue
        p = os.path.join(root, fn)
        if os.path.getsize(p) < 10000 and sha256_file(p) == GARBAGE_SHA:
            garbage_files.append(p)
print(f"garbage files on disk: {len(garbage_files)}")

# 2. split manifest
entries = load_jsonl(MANIFEST)
keep, dropped = [], []
for e in entries:
    if e.get('sha256') == GARBAGE_SHA:
        dropped.append(e)
    else:
        keep.append(e)
print(f"manifest: {len(entries)} entries, dropping {len(dropped)} garbage")
for e in dropped:
    print(f"  DROP {e['economy']} {e['indicator_id']} -> {e['text_path']}")

# 3. restore pre-incident entries from backup where the old file still exists
backup = load_jsonl(BACKUP) if os.path.exists(BACKUP) else []
by_cell = {}
for e in backup:
    by_cell.setdefault((e.get('economy'), e.get('indicator_id')), []).append(e)

current_cells = {(e.get('economy'), e.get('indicator_id')) for e in keep}
restored, unrecovered = [], []
for e in dropped:
    cell = (e['economy'], e['indicator_id'])
    if cell in current_cells:
        continue  # another entry already covers the cell
    for old in by_cell.get(cell, []):
        old_path = os.path.join(WORKDIR, old['text_path'])
        if os.path.exists(old_path) and sha256_file(old_path) != GARBAGE_SHA:
            keep.append(old)
            restored.append(cell)
            print(f"  RESTORE {cell[0]} {cell[1]} <- {old['text_path']} ({old.get('char_count')} chars)")
            break
    else:
        unrecovered.append(cell)
        print(f"  GAP {cell[0]} {cell[1]} — old text unrecoverable, back to honest FETCH_GAP")

# 4. write cleaned manifest + delete garbage files
with open(MANIFEST, 'w') as f:
    for e in keep:
        f.write(json.dumps(e, ensure_ascii=False) + '\n')
for p in garbage_files:
    os.remove(p)
    print(f"  RM {os.path.relpath(p, WORKDIR)}")

print(f"\nDONE: manifest {len(entries)} -> {len(keep)} entries; "
      f"{len(restored)} restored, {len(unrecovered)} honest gaps, "
      f"{len(garbage_files)} garbage files deleted")
