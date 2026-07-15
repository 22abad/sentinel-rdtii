# Round 1 structured-output sample (Pillars 6 & 7)

Reference output of the SENTINEL tool for the **Round 1 mandatory scope** —
Pillar 6 (Cross-border Data Policies) and Pillar 7 (Domestic Data Protection &
Privacy) across the three mandatory economies. One `.csv` and one `.json` per
economy, in the frozen 13-field submission schema.

| Economy | Rows | Laws | Indicators covered |
|---|---|---|---|
| 🇸🇬 Singapore | 7 | PDPA 2012, PDPA Regulations 2021, Income Tax Act 1947 | P6-I1, P6-I4, P7-I1, P7-I3 |
| 🇦🇺 Australia | 11 | Privacy Act 1988 (incl. P7-I1 framework), My Health Records Act 2012, Information Privacy Act 2009 (QLD), PPIP Act 1998 (NSW) | P6-I2, P6-I4, P7-I1…I5 |
| 🇲🇾 Malaysia | 4 | PDPA 2010 (incl. P7-I1 framework), Companies Act 2016 | P6-I4, P7-I1, P7-I3 |

## How this was generated (reproducible, no network)

```bash
RDTII_LLM_PROVIDER=deepseek python main.py --economy Singapore --pillar 6,7 --offline
RDTII_LLM_PROVIDER=deepseek python main.py --economy Australia --pillar 6,7 --offline
RDTII_LLM_PROVIDER=deepseek python main.py --economy Malaysia  --pillar 6,7 --offline
```

`--offline` serves official texts from the SHA-256-verified local law library
(`data/law_library`), so a reviewer reproduces this deterministically with no
network. Retrieval is cached; the **mapping is still produced live** through the
classify → extract → verify → deterministic-score pipeline (only retrieval is
cached). Every row carries a verbatim quote, its source URL, and the RDTII
indicator code.

Quality passes applied at the submission boundary: tag reconciliation → dedupe →
per-(law, indicator) cap → **per-law cap** (no single statute dominates) →
validation, which drops incomplete rows, **fragment quotes** (not real
provisions), and **title-quotes on provision-specific indicators** (a bare law
title is accepted evidence only for the P7-I1 "framework exists" mapping, per the
golden set). See `docs/round2-engineering-log.md` (#150, #151, #153).

The committed artifacts are then refreshed by
`python tools/refresh_r1_submission_samples.py`, which fills authoritative
last-amended years, exact article/page references, and reconciles NEW/KNOWN
against the final submission baseline without rerunning the LLM.

## Honest coverage notes (for the reviewer)

- **This is the curated `--offline` baseline, not an exhaustive list.** The
  default (live-discovery) path surfaces more provisions but also pulls in noise
  (trade agreements, off-topic statutes); the curated library was chosen here for
  a clean, reproducible reference.
- **Malaysia is light (4 rows)** — the curated library holds only a few short MYS
  excerpts (PDPA + Companies Act). Its PDPA now surfaces the golden-approved
  P7-I1 framework row, but fuller coverage (the PDPA's Security/Retention/Access
  principles) is a pending library task: fuller MYS texts exist in
  `data/known_corpus/MYS/`, but a naive add produced mis-mapped rows, so it needs
  a legal-review pass before inclusion (see the engineering log).
- **The federal Privacy Act 1988 now carries its P7-I1 framework row** (its
  existence is the accepted evidence for a comprehensive framework, per the
  golden set), alongside its APP 8 cross-border provision. Deeper coverage (the
  other Australian Privacy Principles) is still to be curated. The Queensland IP
  Act shown is a *state* law included as supplementary baseline evidence, capped
  so it no longer dominates the national picture. It is deliberately tagged
  `KNOWN` and must not be presented as a new discovery.
- A few Australia indicator mappings on the QLD Act are **best-effort and warrant
  a legal check** (e.g. an "authorised officer" provision tagged P7-I4). Treat
  every row as a draft for substantive review, per the project guardrail.
