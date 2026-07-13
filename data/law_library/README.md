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
  in-force status, pillars, indicator hints, `text_path`, `sha256`, retrieval date,
  and **version/currency** fields (`version`, `currency_source`,
  `currency_checked_at`).
- `text/*.txt` — the official provision texts referenced by the manifest.

## Version currency (don't map stale law)

Laws get amended and re-compiled. Each record stores a `version` fingerprint
(e.g. "Compilation No. 104, 4 June 2026", "2020 Revised Edition", "Act 709") and
the date it was last checked. Re-check against the live official source with:

```bash
python tools/check_law_currency.py            # whole library
python tools/check_law_currency.py --economy MYS
# → logs/law_currency_report.json
```

It re-fetches each source via the project crawler and flags any law whose stored
version fingerprint no longer appears — a lead to review, not proof of change.

## Provenance

Seeded from the human-reviewed golden set (`evaluation/golden/`), whose sources
and legal sign-off are documented in
[`docs/golden-set-legal-review-dossier.md`](../../docs/golden-set-legal-review-dossier.md).
Coverage (Pillar 6/7, mandatory economies):

| Economy | Laws |
|---|---|
| Singapore | PDPA 2012 (s.25/26), Income Tax Act 1947 (s.67) |
| Malaysia | PDPA 2010 (s.129, cross-border), Companies Act 2016 (s.245) |
| Australia | My Health Records Act 2012 (s.77), Privacy Act 1988 (APP 8) |

The Malaysia PDPA 2010 entry was retrieved via the project crawler and is a
library baseline pending substantive legal review (not a golden-set answer key).

## KNOWN baseline vs discovered NEW (`origin`)

Each entry has an `origin`:

- `known` — a sample-kit / official-inventory law (the KNOWN baseline). Counted
  by `novelty.known_law_index`, so a match to it is tagged **KNOWN**.
- `discovered` — an **independent NEW find**: an in-force Pillar 6/7 law that is
  **not** in the official ESCAP Legal Inventory (`data/known_inventory.jsonl`).
  It is cached here for offline reproducibility but is **excluded** from the
  KNOWN index, so it correctly surfaces as **NEW** (with full provenance —
  official URL, retrieval date, SHA-256).

Discovered NEW entries currently cached (verified against the official source,
each absent from the inventory):

| Economy | Law | Pillar | Why it's NEW |
|---|---|---|---|
| Singapore | Personal Data Protection Regulations 2021 (S 63/2021) | 6 | Cross-border transfer conditions under PDPA s.26; distinct subsidiary instrument, not inventoried |
| Malaysia | Credit Reporting Agencies Act 2010 (Act 710) | 7 | Credit-data protection statute, not in the inventory |
| Australia | Archives Act 1983 | 7 | Commonwealth-records retention (note: gov-scope for 7.3 scoring) |

## Regenerating / extending

Add a law by appending a `text/<name>.txt` file and a manifest record with its
SHA-256 (`shasum -a 256 text/<name>.txt`), official URL, `version`, and retrieval
date. Keep the recorded hash in sync with the file or the integrity check rejects
it. Then run `check_law_currency.py` to confirm the source is reachable and current.
