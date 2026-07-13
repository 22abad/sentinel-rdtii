# Local law library

A cache-first, **offline** store of official legal texts for the mandatory
economies (Pillar 6 & 7). Used by `python main.py --economy X --pillar 6 --offline`
so a reviewer can run the tool deterministically with **no network** — immune to
portal rate-limits, bot-blocking, JavaScript-only pages, and outages.

## What this is (and is not)

This is a **verifiable cache of official text**, not a store of hand-authored
answers. For each law we record the official source URL, the retrieval date, and
a SHA-256 of the exact text. `law_library.load_library()` re-computes and checks
that hash on every load, so a corrupted or edited cache fails loudly instead of
silently serving wrong text.

The **mapping is still produced live**: the cached text is fed through the same
classify → extract → verify → deterministic-score pipeline as a live crawl. Only
*retrieval* is cached. Cached laws are the curated **KNOWN** baseline
(`discovery_tag = KNOWN`); anything the live sweep finds beyond this library is
tagged **NEW**.

## Layout

- `manifest.jsonl` — one JSON record per law: economy, law name, official URL,
  in-force status, pillars, indicator hints, `text_path`, `sha256`, retrieval date.
- `text/*.txt` — the official provision texts referenced by the manifest.

## Provenance

Seeded from the human-reviewed golden set (`evaluation/golden/`), whose sources
and legal sign-off are documented in
[`docs/golden-set-legal-review-dossier.md`](../../docs/golden-set-legal-review-dossier.md).
Current coverage: Singapore (PDPA 2012, Income Tax Act 1947), Malaysia
(Companies Act 2016), Australia (My Health Records Act 2012, Privacy Act 1988).

## Regenerating / extending

Add a law by appending a `text/<name>.txt` file and a manifest record with its
SHA-256 (`shasum -a 256 text/<name>.txt`), official URL, and retrieval date. Keep
the recorded hash in sync with the file or the integrity check will reject it.
