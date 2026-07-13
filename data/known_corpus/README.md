# KNOWN law full-text corpus

A local, offline full-text corpus of the **KNOWN** laws — the ~195 statutes and
instruments in the official ESCAP RDTII Legal Inventory for Singapore, Malaysia,
and Australia. It is the reference/RAG substrate: the actual text of every KNOWN
law, fetched from its official source.

## How it's built

```bash
python tools/build_known_corpus.py            # fetch all (resumable)
python tools/build_known_corpus.py --economy SGP
python tools/build_known_corpus.py --browser  # also use the browser path (JS sites; slower)
```

The builder reads the official inventory
(`requirements/Singapore, Malaysia, Australia, Legal Inventory.csv`), fetches each
law's official URL via the project crawler, and writes:

- `data/known_corpus/<ECON>/<slug>.txt` — the law's full text (**git-ignored** —
  local reference / RAG input; rebuild anytime from the manifest).
- `data/known_corpus/manifest.jsonl` — the tracked index: for each law its
  economy, name, official URL, SHA-256, char count, and fetch status
  (`ok` / `cached` / `failed`).

Re-running skips laws already fetched. Laws whose official portal is a
JavaScript-only single-page app may need `--browser`; a few may be unreachable
and are recorded as `failed` for transparency (no silent gaps).

## Relationship to the curated law library

`data/law_library/` is the small, curated set (with per-indicator hints) that
drives `--offline` mapping and the tests. This corpus is the *broad* KNOWN
reference — every inventory law's text — suitable for retrieval/RAG and for
promoting any entry into the curated library when needed.
