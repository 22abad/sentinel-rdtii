#!/usr/bin/env python3
"""Which official-inventory law names would the _STATUTE_INSTRUMENT_WORD gate drop?

Empirical basis for extending the word list (LAO 'Decision' incident,
2026-08-01): scan every law_name in data/round2_inventory.jsonl (split on ';')
against the CURRENT gate regex imported from submission.schema — no drift."""
import json, re, sys, os, collections

WORKDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(WORKDIR, 'ai-service'))
from submission.schema import _STATUTE_INSTRUMENT_WORD  # noqa: E402

seen, misses = set(), []
with open(os.path.join(WORKDIR, 'data', 'round2_inventory.jsonl')) as f:
    for line in f:
        d = json.loads(line)
        for name in re.split(r';\s*', d.get('law_name', '')):
            name = ' '.join(name.split())
            if not name or name in seen:
                continue
            seen.add(name)
            if not _STATUTE_INSTRUMENT_WORD.search(name):
                misses.append((d['economy'], name))

print(f"official names (split, deduped): {len(seen)}; gate would drop: {len(misses)}")
print(collections.Counter(e for e, _ in misses))
for e, n in misses:
    print(f"  {e} | {n[:100]}")
