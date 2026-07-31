# 🏛️ SENTINEL — AI Tool for Digital Trade Regulatory Analysis

> **"Where Code Meets Law."** Transforming ~100 pages of unstructured trade
> regulations into actionable, mapped data.

UN Global Hackathon on AI for Digital Trade Regulatory Analysis
Team: **SENTINEL** (Maynooth University) | Rounds: **1 & 2**
Last updated: **2026-07-23**

**Quick Start:** the [Quick Start](#quick-start) below lets a reviewer set up and
run the tool in minutes. **Round 1** scope is **RDTII 2.1 Pillar 6 (Cross-border
Data Flows)** and **Pillar 7 (Domestic Data Protection)**; **Round 2** extends the
same engine to the **full methodology — 61 indicators across all 12 pillars for 7
economies** (see [Round 2](#round-2--all-12-pillars--7-economies)).

---

## What This Tool Does

**Task 1 — Automated Evidence Discovery.** Given an economy and a regulatory
topic, the tool searches official government legal portals, retrieves the
relevant legislation (including scanned PDFs via OCR), and extracts clean,
structured text.

**Task 2 — Intelligent Mapping & Categorization.** The extracted text is mapped
to specific RDTII indicator IDs. Each matched provision carries an
article-level citation, a verbatim quote, and a Discovery Tag marking whether it
was found independently (`NEW`) or matched a curated known-law example
(`KNOWN`).

To reduce hallucination risk in a legal context the engine is a
**deterministic + probabilistic hybrid**: regex slices the statute → a
keyword classifier routes chunks → the LLM extracts features and a verbatim
quote → the quote is verified character-for-character against the source → a
deterministic Python scorer assigns the RDTII score. Any mapping whose quote
cannot be verified is rejected, not shown.

**Economies covered** — two honest tiers:

- **Tier 1 — live crawl + offline (reviewers can run directly):** Singapore,
  Malaysia, Australia (Round 1 mandatory, live-smoke verified), plus Thailand
  and China (live discovery registries configured).
- **Tier 2 — live registries configured + corpus-verified:** India, Indonesia,
  Lao PDR, Mongolia, Russian Federation — each now has an official-portal
  discovery registry (India Code / JDIH / Lao Gazette / Legalinfo.mn /
  pravo.gov.ru + the sector regulator) with local-language query terms, and is
  benchmarked against 500 official baseline rows. Live discovery is smoke-tested
  (e.g. `--economy India --pillar 7` finds the Digital Personal Data Protection
  Act 2023 on indiacode.nic.in); depth and text-fetch reliability vary by portal
  and are still being hardened for the finale.

**Round 2 snapshot (current best submission):** the reproducible full run emits
a **1,246-row, 12-pillar × 7-economy evidence submission** covering **71.2% of
the official scorable cells** (163/229 economy×indicator cells the RDTII database
scores non-zero). **96.2% of quotes are located verbatim** in their source text
(the extractor hard-rejects non-verbatim quotes), and an independent blind
cross-model checker **overturns 29% of positive generic scores** before anything
ships. On the self-evaluation against the official raw scores, **500
official-baseline rows** were evaluated with evidence found for **70.2%** and an
exact score match on **50.2%** (correct zero-abstentions included, so not a
standalone accuracy rate). Whole-submission deployment cost: **$12.96 on a hosted
model, $0 on the open-weight (Ollama) path**. Every number is reproducible from
the eval JSONs — see the [per-economy report](docs/round2-meeting-report.md).

---

## Quick Start

⚠ **Required for Round 1.** A reviewer with basic Python knowledge can run this
in a few minutes. The default provider below is a local open-weight model
(Ollama) so **no API key is required**; see [Swapping the LLM](#swapping-the-llm)
for cloud providers.

> **Two independent ways to run this — don't mix them up:**
> 1. **The `main.py` CLI (this Quick Start) — the Round-1 structured-output
>    deliverable.** It runs in a plain Python **virtualenv on your machine**.
>    It does **not** use Docker and does **not** need PostgreSQL — so
>    `python main.py --economy Australia --pillar 6,7` only works after you do
>    the `pip install` step below. `docker compose up` alone will **not** make
>    the CLI runnable.
> 2. **The web workbench (optional) — the interactive UI.** That one runs via
>    `docker compose up --build` (see [below](#optional--web-workbench-the-audit-view-via-docker)).
>
> A judge reproducing our results uses path 1 for the CSV/JSON output, and can
> optionally start path 2 to click through the same engine in a browser.

### 1. Clone

```bash
git clone https://github.com/22abad/UN-DigitalTrade-AI-Mapper-private.git
cd UN-DigitalTrade-AI-Mapper-private
```

### 2. Set up the environment (Python 3.11+)

```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

This lean install runs the discovery + OCR + mapping CLI. The CLI reads its
official-source registry from the checked-in YAML, so PostgreSQL is not required.
(The full web app and local RAG embeddings use `ai-service/requirements.txt`;
see [SETUP.md](SETUP.md).)

### 3. Configure the model

```bash
cp .env.example .env
```

**Option A — local open-weight model (no API key):**

```bash
# Install Ollama from https://ollama.com, then:
ollama pull qwen2.5:14b
```

```env
RDTII_LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:14b
OLLAMA_BASE_URL=http://localhost:11434/v1
```

**Option B — cloud provider:** set `RDTII_LLM_PROVIDER=deepseek` (or `openai`,
`gemini`, `claude`) and the matching API key. See [Swapping the LLM](#swapping-the-llm).

> **Speed vs. reproducibility.** The local Ollama model (Option A) is key-free
> and fully reproducible, but a full-pillar run maps many provisions and can take
> several minutes on CPU. If you have a key, a cloud provider (Option B, e.g.
> DeepSeek) is much faster. For a quick check either way, narrow the run with
> `--indicators` (e.g. `--indicators 6.4`); note that restricting to an indicator
> with no matching source in the local library returns 0 rows by design, not an
> error.

#### Live search backend — free, no key required

Live discovery finds NEW laws two ways: **dedicated official-portal adapters**
(e.g. Australia's legislation.gov.au API, China's national law database
`flk.npc.gov.cn`) that need no search engine at all, plus a **generic web-search
backend** for everything else. That generic backend is **free out of the box** —
if you set nothing, it uses [DuckDuckGo](https://duckduckgo.com) HTML search,
which needs **no API key, no signup, and no quota**. We verified it returns the
right official sources for legal queries (e.g. Singapore PDPA → `sso.agc.gov.sg`,
Australia Privacy Act → `legislation.gov.au`).

| `DISCOVERY_SEARCH_BACKEND` | Needs a key? | When to use |
|---|---|---|
| *(unset — the default)* | **No** | Free DuckDuckGo. Recommended for reviewers. Can bot-challenge an IP after many rapid searches — either keyed backend below avoids that. |
| `serpapi` (+ `SERPAPI_API_KEY`) | Yes (free tier) | Slightly broader Google-backed results. Auto-selected if a key is present. |
| `google` (+ `GOOGLE_CSE_KEY`, `GOOGLE_CSE_ID`) | Yes (100 queries/day free) | Google's **official** Custom Search API — your own Google key, ToS-clean. Auto-selected when both vars are set and no SerpApi key. |
| `none` | No | Disable live web search; run on the local library only. |

> **Running from inside mainland China?** DuckDuckGo and Google are blocked by
> the Great Firewall, but China discovery does **not** depend on them: the
> `china_flk` adapter queries the official national database `flk.npc.gov.cn`
> directly (reachable inside China) and ships hardcoded seeds for the headline
> data laws (PIPL, Cybersecurity Law). So Chinese-law discovery works behind the
> firewall without a VPN.

### 4. Run

```bash
python main.py --economy Singapore --pillar 6
```

**Output:** `outputs/Singapore_P6_<timestamp>.csv` and `.json`.

By default this runs **seed-first**: it maps the known-good official sources from
the local library (verified, reproducible, no network) *first*, then falls back
to live discovery to fill gaps and surface NEW finds — so a reviewer's short run
never rides entirely on a live crawl. Add `--no-seed` for pure live discovery,
or `--offline` to stay on the seeds only.

The pipeline's quality gates run in **flag mode by default**: a mapping that
fails an automated eligibility check is kept in the output and annotated in the
Notes column for human review (mirroring the official methodology's 20%
human-validation step), rather than silently dropped. Set
`RDTII_ELIGIBILITY_MODE=reject` for a precision-first run that hard-drops
anything the gates do not support.

For an auditable reviewer run, use strict live mode:

```bash
python main.py --economy Singapore --pillar 6 --strict-live
```

`--strict-live` disables the seed pass, rejects fixture/fallback and mock
candidates, accepts only configured official domains, and requires a verified
live document fetch. A run with no qualifying evidence fails explicitly and
writes no submission files. JSON rows record the final URL, HTTP status, fetch
method, and retrieval mode. Every CLI run also prints separate seed,
live-discovered, and fixture evidence counts.

For a lower-cost first run that still exercises real discovery, document
retrieval, and mapping, process only the first accepted document:

```bash
python main.py --economy Singapore --pillar 6 --max-documents 1
```

### Expected runtimes

The official 10-minute requirement covers **setup** (clone → install → run),
which the steps above fit comfortably. How long the run itself takes depends on
the mode — measured on 2026-07-16 with DeepSeek; **your hardware, network, and
the live portals' responsiveness will shift these**:

| Command | Measured | Character |
|---|---|---|
| `--economy Singapore --pillar 6 --offline` | **67 s** | deterministic, no network |
| `--economy Singapore --pillar 6,7 --offline` | **3 min 09 s** | deterministic, no network |
| `--economy Singapore --pillar 6,7` (default: seeds + live discovery) | **27 min** (single measured run) | live-search results vary run to run; the cost guardrails cap noise documents, measured LLM spend ≈ $0.67 |
| add `--max-documents 1` to the default | a few minutes | quickest way to see real live discovery |

For a short, predictable reviewer session: run `--offline` first (seconds to
minutes, fully reproducible), then the default command in the background if you
want to watch live discovery find and report NEW laws.

> To try the pipeline with **no discovery or browser**, point at a local PDF
> instead: `--pdf path/to/law.pdf`. Mapping still uses the configured model.
> Three ready-made demos (born-digital statute, scanned-PDF OCR, and an
> honesty check that returns empty on a mismatched pillar) live in
> [`data/demo_pdfs/`](data/demo_pdfs/).

### Optional — Web workbench (the audit view), via Docker

The CLI above is the judged path and needs no Docker. If you also want the
**human-review workbench** — the audit view with per-document dossier,
clean/needs-review triage, verbatim highlighting, and approve/reject that
persists an audit trail — the full self-hosted stack is three commands
(Docker Desktop or compatible required; the database schema initialises
itself on first start):

```bash
cp .env.example .env        # same file as above; add a model key or use Ollama
docker compose up -d --build
# then open http://localhost:5173 and create an account on /login
```

`docker compose ps` shows the whole stack — frontend, AI service, Postgres
(pgvector), Redis — running locally with no external services.

---

## Full Usage

```bash
# Both pillars, restrict to specific indicators
python main.py --economy Malaysia --pillar all --indicators 7.3

# Bypass discovery and extract from a provided PDF
python main.py --economy Singapore --pillar 6 --pdf path/to/law.pdf

# Choose output format / directory / provider
python main.py --economy Australia --pillar 7 --format csv --output-dir outputs/ --provider deepseek

# Run several economies in one command
python batch_run.py --economies Singapore Australia Malaysia --pillar 6 7

# Fully offline: map cached official texts from the local law library (no network)
python main.py --economy Singapore --pillar 6 --offline
```

| Flag | Meaning |
|---|---|
| `--economy` | Economy name or ISO-3 code (e.g. `Singapore` / `SGP`) |
| `--pillar` | `6`, `7`, or `all` |
| `--indicators` | Restrict to specific indicators, e.g. `6.1 6.4` |
| `--pdf` | Extract from a local PDF (skips the crawler) |
| `--offline` | Map cached official texts from the local law library (no network) |
| `--no-seed` | Skip the seed pass; go straight to live discovery (default is seed-first) |
| `--strict-live` | Reviewer mode: verified official live evidence only; fail instead of using fixtures |
| `--include-review` | Include ambiguous/flagged mappings unconditionally (only changes anything under `RDTII_ELIGIBILITY_MODE=reject`; the default flag mode already keeps them, annotated in Notes) |
| `--provider` | Override `RDTII_LLM_PROVIDER` for this run |
| `--format` | `csv`, `json`, or `both` (default) |
| `--limit` | Maximum Discovery candidates returned per pillar (default: 20) |
| `--max-documents` | Stop after processing this many documents |
| `--registry-backend` | Source registry: `file` (CLI default) or `database` (full app) |

Two run-cost guardrails keep the default command inside a reviewer's time
budget, both loud and honest: candidates that the submission noise-gate would
reject anyway (trade agreements, blogs) are **skipped before fetching**, and
live-discovered documents larger than `RDTII_MAX_LIVE_DOC_CHARS` (default
150K chars; `0` disables) are extracted **truncated with a "partial doc" note
on every affected row**. Seeds and `--pdf` documents are never capped.

---

## Offline mode & the local law library

Live discovery crawls official government portals — the headline Task-1
capability — but a portal can rate-limit, block bots, require JavaScript, or be
down during a reviewer's short run. `--offline` removes that dependency by
serving the source text from a **local law library** (`data/law_library/`), so a
run is deterministic, air-gapped, and $0 in network cost.

```bash
python main.py --economy Singapore --pillar 6 --offline
```

**This caches retrieval, not answers.** Each library entry is a *verifiable
cache of official text* — it records the source URL, retrieval date, and a
SHA-256 that is re-checked on every load (a tampered or drifted cache fails
loudly). The mapping itself still runs live through the same
classify → extract → verify → deterministic-score pipeline, so provisions are
produced, not replayed. Cached laws are the curated **KNOWN** baseline;
anything the live sweep finds beyond the library is tagged **NEW**.

| | Seed-first (default) | `--no-seed` | `--offline` | `--pdf <path>` |
|---|---|---|---|---|
| Retrieval | Library seeds → then live crawl | Playwright crawl + cache/Wayback fallback | Local law library | One provided file |
| Network needed | Fallback only | Yes | **No** | No |
| Mapping | Live pipeline | Live pipeline | Live pipeline | Live pipeline |
| Discovery tag | KNOWN / cached NEW + live NEW | NEW / KNOWN | KNOWN / cached NEW | per source |

### Seed registry — one place for the trusted URLs

Every known-good official source URL is consolidated into a single, tiered,
de-duplicated registry at **`data/seed_sources.jsonl`** (rebuilt by
`python tools/build_seed_registry.py`). It merges the curated library (exact URL
+ SHA-256-verified cached text) with the broad KNOWN corpus (204 official URLs +
fetch status), so "which sources do we trust, and did they fetch?" is one
auditable list. The seed-first run serves the `library_cached` tier before
touching the network.

---

## Reproducibility & testing

The submission is guarded by two runnable checks:

```bash
# 1. Reproducibility gate — reproduces the judge setup in a clean virtualenv
#    (fresh `pip install -r requirements.txt`) and asserts the headline command
#    writes output. Catches "works on my machine" dependency gaps.
bash tools/check_reproducibility.sh

# 2. Judge-simulation matrix — graded main.py runs from easy to hard, scored
#    the way a judge grades output (ran? wrote files? verbatim + source +
#    article present? no hallucinated names? no duplicates? honest empties?).
python tools/judge_test_matrix.py          # tiers 1-3 + 5 (offline/robustness)
python tools/judge_test_matrix.py --live   # also tier 4 (live network)
```

The matrix report (`docs/judge-test-report.md`) covers 5 difficulty tiers:
the headline command, the full mandatory scope + scanned-PDF OCR, adversarial
inputs (mis-spelt economy, invalid pillar, malformed/blank PDF), the live
network path a judge actually uses, and honesty stress (a mismatched-pillar
PDF must return nothing rather than hallucinate). Dependencies are pinned;
`pip install` runs in a few minutes with no PostgreSQL required.

---

## Round 2 — all 12 pillars × 7 economies

Round 2 (final) spans the **full RDTII 2.1 methodology: 61 indicators across
pillars 1–12** for **China, India, Indonesia, Lao PDR, Mongolia, the Russian
Federation and Thailand**. The engine is methodology-driven: the official
criteria (`data/rdtii21_methodology.json`) generate each indicator's
extraction spec and its deterministic tier-to-score rule, so the LLM only ever
identifies *which published criterion* a provision matches — never the number.

```bash
# Extract the official baseline (methodology + 809 baseline laws, 1,707 URLs)
python tools/build_round2_baseline.py

# Fetch the baseline laws' full texts into a local corpus (resumable)
python tools/build_round2_corpus.py --economy IND

# Verify (and repair) corpus integrity: each text is checked against the
# manifest's recorded sha256 + char_count, so a truncated / wrong-law file can
# never silently poison the submission. --check audits; without it, corrupt
# files are re-fetched from their recorded good URL (non-truncated text only).
python tools/restore_corpus.py --economy IDN --check

# Produce the FULL Round-2 evidence submission (all 12 pillars) from the
# fetched corpus — reproducible, no network. This is the deliverable a judge
# runs: it maps every corpus law to its official indicators through the same
# extraction → RAG-retrieval → deterministic-scoring pipeline and writes the
# 13-column CSV + JSON for all 61 indicators.
python main.py --economy Indonesia --pillar all --from-corpus

# Run any economy / any pillar through the same CLI (live/seed paths too)
python main.py --economy India --pillar all
python main.py --economy "Lao PDR" --pillar 6,7,12

# Self-evaluate against the official Round 2 raw scores
python tools/run_round2_eval.py --economy IND
```

`--from-corpus` is the reproducible Round-2 submission path: it does not
blind-truncate a long statute (a language-aware BM25 retriever selects the
indicator-relevant provisions, in the document's own language), caps to the
strongest few provisions per (law, indicator), and tags NEW/KNOWN across
languages by statute number+year. The offline corpus is **sha256-verified**
(`tools/restore_corpus.py`): the reproducible run cannot be fed a truncated or
wrong-law text without the integrity check flagging it. The self-evaluation
reports **coverage, evidence yield, exact-score-match rate and MAE against the
official database** — rows without local text, failed extractions and
mismatches are counted, never hidden.

**Latest full run:** 1,246 evidence rows over all 12 pillars and 7 economies,
**71.2% official scorable-cell coverage**, 96.2% verbatim grounding (the run
writes to `outputs/`, which is git-ignored — a reviewer regenerates it from the
corpus, it is never a hand-curated artifact). Two tools make the headline numbers
reproducible from any run and keep the remaining gap honest:

```bash
# Official scorable-cell coverage of a submission dir, with a
# fetch/corpus/extraction root-cause breakdown of every uncovered cell
python tools/coverage_report.py outputs/<your-run-dir> --gaps

# Whole-submission deployment cost (LLM calls, tokens, $) parsed from the run's
# stdout — $12.96 for the full 7-economy × 12-pillar submission on a hosted
# model, $0 on the open-weight (Ollama) path
python main.py --economy Indonesia --pillar all --from-corpus | tee run.log
python tools/cost_report.py run.log
```

---

## Discovering new laws (NEW vs KNOWN)

Beyond mapping the sample-kit laws, the tool rewards **independently finding
in-force Pillar 6/7 laws** the kit did not include. It decides novelty by
evidence, not by which crawler surfaced a result: a mapped provision is **KNOWN**
only if its statute is already in the authoritative baseline — the official
ESCAP RDTII Legal Inventory (`data/known_inventory.jsonl`, 195 laws across the
three economies) or the curated local law library; everything else is a genuine
**NEW** find.

Fixture and fixture-fallback candidates are never considered NEW, never count
as successful live discovery, and are excluded from formal submission output.

```bash
python tools/discover_new_laws.py --economy Singapore --pillar all
# → logs/discovery_report.json
```

The report lists each NEW candidate with its full audit trail — official source
URL, verbatim quote, indicator, and confidence — behind an explicit
**human-review gate**: a NEW find is a *draft lead for legal verification, not a
settled legal conclusion*. Every candidate already passed the same
verbatim-quote check and deterministic scorer as any other mapping, so unverified
finds never appear. The golden set demonstrates the pattern in practice — the
My Health Records Act (6.1/6.2), Companies Act s.245 (7.3), and Income Tax Act
s.67 (7.3) are exactly such sectoral-law discoveries beyond a core
data-protection statute.

Reconciliation is reusable in code: `submission.reconcile_discovery_tags(rows)`
re-tags any result set against the baseline, and `build_discovery_report(...)`
produces the gated report.

**Current discovery record: 21 verified NEW laws banked** (AUS 11 · MYS 6 ·
SGP 4 — 18 in the mandatory Pillars 6/7 across all three provided economies,
plus 1 beyond-6/7 in Pillar 12), each with a verbatim provision fetched from the official portal and a
SHA-256-verified library entry — including NSW's cross-border s 19(2), captured
through a Cloudflare-guarded portal by the browser fallback. Every candidate
passed a **double rigor gate**: hand re-verification against the official source
plus an automated `is_known_law` novelty check (which rejected ~12 would-be
finds as already-known or not-in-force). Full audit trail:
[`docs/new-law-candidates.md`](docs/new-law-candidates.md).

Banking a verified find is one command — it re-fetches the official URL,
confirms the provision verbatim, refuses anything already KNOWN or too weak,
and can push the text straight into the searchable vector store:

```bash
python tools/promote_new_law.py --economy AUS --law-name "..." --url "..." \
    --pillars 6 --indicators 6.4 --text-file provision.txt --verify --embed
```

### Checking a run against the official answer key — and NEW-evidence divergence

The official RDTII Round-1 database holds **one raw score (0 / 0.5 / 1) per
indicator per economy**, with the law it cites. `score_vs_official.py` folds any
run into per-indicator coverage and lines it up against that key:

```bash
python tools/score_vs_official.py --economy Singapore          # newest run in outputs/
python tools/score_vs_official.py outputs/Australia_P6-7_*.json --md report.md
```

It flags three things a reviewer must act on:

- **⚠️ NEW-EVIDENCE DIVERGENCE — when a NEW law we discovered changes the score
  vs the official baseline, it is marked, both in this report and (via
  `discovery_tag = NEW`) in the run output.** This is *deliberate and important*:
  if the NEW law is **real**, a differing score is legitimate — it is the
  Stage-2 "Discovery of New Evidence" the framework rewards, and **it must be
  called out in the submission** so a judge sees we refined the baseline (e.g.
  Australia's official 7.2 = 0.5 rests on the 2018 SOCI Act; our discovered
  **Cyber Security Act 2024** is a dedicated framework that would move it to 0).
  If the NEW law is **hallucinated**, that same divergence is an over-claim and
  the row must be dropped. Either way the divergence is never silent.
- **💀 HALLUCINATION** — three or more different law names sharing one source URL
  (a fabricated name hung on a real URL). The validator now writes a loud
  `hallucination check` note onto every such row; `score_vs_official` tallies
  them per indicator. On the raw live runs this was **31/47 (AUS)** and
  **52/70 (SGP)** rows — the live-discovery output is a *lead list to verify*,
  not submission-ready.
- **❌ GAP** — the official has a non-zero score but the run found nothing.

Two validator gates back this up: a **goods/agriculture law mapped to P6/P7**
(e.g. "Wine Export Charge Act") is dropped as out of scope, and the
one-URL-many-names rows are flagged. Note one honest limitation: **indicator 7.2
(dedicated cybersecurity framework) is a *framework-existence* judgement the
content extractor maps to Pillar 11 (Standards), not 7.2** — so a cyber Act is
flagged for legal-review indicator confirmation rather than auto-scored at 7.2
(this is why AUS Cyber Security Act 2024 is dual-hinted 11.1 / 7.2, and SGP 7.2 —
official 0 via Cybersecurity Act 2018 — is confirmed by a reviewer).

---

## Architecture Overview

```
Input: Economy + Pillar
        │
        ▼
  TASK 1 — Evidence Discovery
   1. Discovery service   → official-portal adapters + search (ai-service/discovery/)
   2. Document fetch/OCR  → PyMuPDF text layer + Tesseract / OpenAI-vision fallback
        │  clean structured text
        ▼
  TASK 2 — Mapping & Categorization  (Multi-Agent System, ai-service/agents/)
   3. Classifier   → keyword router selects candidate indicators (anti-hallucination)
   4. Extractor    → verbatim quote + Act metadata
   5. Analyst      → impact / comment analysis
   6. Critic       → deterministic score + source audit + quote verification
        │
        ▼
Output: CSV / JSON with the 13-field provision schema
```

The LLM provider is fully abstracted (`ai-service/providers/`), so the model can
be swapped with one config value (see below). The submission adapter that maps
the internal engine to the judges' output contract lives in
`ai-service/submission/` and is driven by the root `main.py`.

> **One honest divergence from the template diagram:** hybrid RAG retrieval
> (chunk + embed + pgvector search) powers the **web workbench**, not this CLI —
> the CLI maps full statute text through the multi-agent pipeline directly.
> CLI-side RAG is a finale-stage upgrade.

### Key modules

| Module | File | Description |
|---|---|---|
| Portal crawler | `ai-service/legal_crawler/` | Official-portal fetch cascade: HTTP → Playwright browser → Wayback/Google-cache fallbacks |
| Discovery service | `ai-service/discovery/` | Portal adapters + pillar→topic query builder (`query_builder.py`) |
| OCR processor | `ai-service/pdf_reader/` | PyMuPDF text layer; Tesseract on scanned pages; per-row CER estimate |
| Chunker | `ai-service/chunker.py` | Regex legal chunker — article/section-level slices |
| Mapper (multi-agent) | `ai-service/agents/` + `ai-service/extraction_pipeline.py` | Classifier → Extractor → Analyst → Critic; verbatim verify + deterministic score |
| Source verification | `ai-service/services/source_verification.py` | Per-portal fetch strategies + verbatim-quote gate + `is_known_law` triage for NEW finds |
| Output writer | `ai-service/submission/writer.py` | 13-field CSV/JSON contract |
| Provider layer | `ai-service/providers/` | Swappable LLM backends + automatic failover |

---

## Supported Economies & Portals

| Economy | Official portal(s) | Language | Notes |
|---|---|---|---|
| Singapore | sso.agc.gov.sg | English | Machine-readable HTML/PDF; provision bodies lazy-loaded (`?ProvIds=` handled) |
| Malaysia | lom.agc.gov.my · pdp.gov.my · mcmc.gov.my | English / Malay | Statute PDFs; commencement gazettes on pdp.gov.my |
| Australia (federal) | legislation.gov.au | English | Embedded-HTML text pages; EPUB for very large Acts |
| Australia (states) | legislation.vic.gov.au · legislation.nt.gov.au · legislation.nsw.gov.au | English | VIC/NT text lives in authorised PDFs; **NSW is Cloudflare-guarded — captured via the Playwright browser fallback** |
| Thailand | searchlaw.ocs.go.th (Council of State) | Thai | Native-script statutes; B.E. era handling |
| China | npc.gov.cn / cac.gov.cn registry | Chinese | Registry configured; flagship laws reconcile as KNOWN |
| Tier 2 (IND · IDN · LAO · MNG · RUS) | official corpus (809 baseline laws, 1,707 URLs) | 7 languages | Offline/corpus path; live registries are finale-stage |

---

## Output Formats

### Round 1 prototype output — 13 fields

For Round 1, the explicitly mandatory submission items are a complete Quick
Start and a runnable functional prototype. The prototype output contract below
is nevertheless part of the supplied Round 1 README template, so the
judge-facing root CLI (`python main.py ...`) always preserves these 13 fields.
This is the output reviewers should use when validating the Round 1 prototype.

Each run writes a CSV and a JSON file. **CSV columns are in this exact order —
do not rename or reorder.**

| # | Column | Required | Description |
|---|---|---|---|
| 1 | `economy` | ✓ | Official UN economy name |
| 2 | `law_name` | ✓ | Full statute name and year |
| 3 | `law_number_ref` |  | Official act/law number (e.g. `Act 777`) |
| 4 | `last_amended` | ✓ | Year of most recent amendment, or `Not stated in source` |
| 5 | `indicator_id` | ✓ | RDTII code (e.g. `P6-I1`, `P7-I3`) |
| 6 | `article` | ✓ | Exact article/section (e.g. `Section 26`) |
| 7 | `discovery_tag` | ✓ | `NEW` = independent find; `KNOWN` = curated example |
| 8 | `location_reference` |  | PDF page / URL anchor |
| 9 | `verbatim_snippet` | ✓ | Exact quoted text (verified against source) |
| 10 | `mapping_rationale` |  | ≤300 chars: why this provision maps here |
| 11 | `source_url` | ✓ | Direct URL on the official portal |
| 12 | `confidence` |  | Discovery confidence 0.00–1.00 |
| 13 | `notes` |  | OCR issues, human-review flags, bilingual sources |

The JSON adds extended metadata (`raw_context_before/after`, `pdf_is_scanned`,
`retrieval_method`, …) for the audit view.

### Frontend RDTII data-table export — 10 fields

The web frontend also offers the standard RDTII 2.1 data-collection table with
`Pillar_ID`, `Indicator_ID`, `Cat_Score`, `Raw_Score`,
`Act_and_or_practice`, `Coverage`, `Impact_or_comments`, `Timeframe`,
`References`, and `Note`. That export is intended for RDTII scoring/database
workflows. It is supplemental and **does not replace** the root CLI's 13-field
Round 1 prototype output. Both formats are maintained because they serve
different consumers.

---

## Swapping the LLM (No Vendor Lock-in)

Change one config value — no code changes. Providers live in
`ai-service/providers/` behind a common interface.

```env
# Local open-weight (no key)          # Cloud
RDTII_LLM_PROVIDER=ollama             RDTII_LLM_PROVIDER=deepseek
OLLAMA_MODEL=qwen2.5:14b              DEEPSEEK_API_KEY=...
```

Supported providers: `ollama`, `openai`, `deepseek`, `gemini`, `claude`,
`groq`, `together`, `openrouter`, `mistral`, and local GGUF via `llama-3-local`.
To add one, implement a class in `ai-service/providers/` and register it in
`providers/__init__.py`.

### Automatic fallback (judge-safety net)

Set a fallback so a run still completes if the primary model is unavailable in a
reviewer's environment (e.g. Ollama not installed, or a request errors):

```env
RDTII_LLM_PROVIDER=ollama            # primary — local, $0
RDTII_LLM_FALLBACK_PROVIDER=deepseek # fallback — used only if the primary fails
DEEPSEEK_API_KEY=...                 # ship the team's key as the net
```

If a primary call fails, the whole multi-agent pipeline transparently fails over
to the fallback provider (and latches to it for the rest of the run — a dead
primary is not retried on every call). Leave `RDTII_LLM_FALLBACK_PROVIDER` blank
to disable. The failover wrapper is `providers.resolve_provider()` →
`providers/fallback.py`.

## OCR Engine

OCR is applied only to pages without a usable text layer.

| Engine | Status |
|---|---|
| Tesseract (local, default) | ✓ implemented |
| OpenAI vision fallback | ✓ implemented (optional, needs `OPENAI_API_KEY`) |
| Azure Document Intelligence / PaddleOCR / Mistral OCR | not yet wired |

---

## Actual Cost Per Document

**Measured, not estimated.** Run the cost logger on the included 50-page
benchmark (or any document):

```bash
python tools/cost_logger.py --pdf data/benchmark/benchmark_50pages.pdf \
    --economy Malaysia --pillar all
# → logs/cost_report.json
```

It records measured token counts, wall-clock time, and cost. Cost is
provider-reported when available, otherwise measured tokens priced at the
published rates in `ai-service/submission/cost.py`; local open-weight models are
recorded at **$0 API cost**.

### Measured result — 50-page benchmark

Document: 50-page excerpt of the **Malaysia Companies Act 2016 (Act 777)**,
including the s.245 seven-year retention provision (RDTII 7.3). See
[`data/benchmark/`](data/benchmark/) for provenance and the raw
`cost_report_50pages.json`.

**Measured on 2026-07-11** — 37 LLM calls, **41,907 input / 4,968 output
tokens**, **220.7 s** wall-clock on a local model; OCR not required (digital
text layer).

| Stack | Engine | Cost per 50-page document |
|---|---|---|
| **Open-weight (measured)** | Ollama `qwen2.5:14b`, local | **$0.000** |
| Cloud (measured tokens × published rate) | GPT-4o-mini | ≈ $0.009 |
| Cloud (measured tokens × published rate) | DeepSeek | ≈ $0.017 |
| Cloud (measured tokens × published rate) | GPT-4o | ≈ $0.154 |

OCR and embedding cost are $0 here (born-digital PDF; RAG embeddings are not on
the mapping path). Cloud rows apply each vendor's published per-token price to
the **same measured token counts** — reproducible from `cost_report_50pages.json`.

### Per-component breakdown (template format)

| Component | Engine used | Measured cost |
|---|---|---|
| OCR | Tesseract (local; only pages without a text layer) | $0.000 |
| Embedding | not on the CLI mapping path (local MiniLM in the web app) | $0.000 |
| LLM mapping | DeepSeek (measured tokens × published rate) | ≈ $0.017 |
| Crawling | self-hosted (httpx + Playwright) | $0.000 |
| **Total (current stack)** | | **≈ $0.017 per 50-page document** |
| **Total (open-weight swap)** | Ollama `qwen2.5:14b` + Tesseract | **$0.000 per document** |

**Measured on:** 2026-07-11 (token counts) / 2026-07-16 (wall-clock re-check)
**Benchmark document:** Malaysia Companies Act 2016 (Act 777) excerpt, 50 pages
**Token counts:** input 41,907 | output 4,968 (37 LLM calls)
**Wall-clock:** 220.7 s on the local open-weight model; a full economy-pillar
offline run (`--economy Singapore --pillar 6 --offline`, DeepSeek) completes in
**67 s** end-to-end.

---

## Running the Test Suite

```bash
cd ai-service && python -m pytest
```

Key coverage: extraction/anti-hallucination pipeline, discovery adapters +
validation, OCR benchmarking, the golden-set evaluation harness, and the
submission 13-field contract (`tests/test_submission_schema.py`).

Reproduce the human-reviewed golden-set metrics:

```bash
make eval-setup
make eval-golden
```

`eval-setup` installs only the lean reviewer dependencies from the repository
root; the offline evaluation does not require FastAPI, browser binaries, a
database, network access, or an API key. `eval-golden` regenerates the committed
JSON and Markdown reports in `evaluation/reports/`.

The approved 29-case set covers all ten Pillar 6/7 indicators with a positive
and boundary negative per indicator and both pillars for AUS, MYS, and SGP.
Every case and source record has substantive-lead sign-off. Run
`make golden-coverage` to verify the structural coverage contract.

---

## Known Limitations

Transparency builds credibility — we are honest about the current state.

- **Model accuracy:** the un-fine-tuned open-weight model makes RDTII boundary
  errors (e.g. it may code a conditional-transfer clause as 6.1 instead of 6.4).
  Every mapping is therefore quote-verified and flagged for human legal review;
  a fine-tuned 12B model is in progress.
- **Golden-set breadth:** all 29 cases have substantive-lead sign-off and meet
  the Pillar 6/7 structural coverage target, but broader economy and language
  coverage is still needed before treating the benchmark as globally
  representative; see `docs/golden-set-expansion-review.md`.
- **JavaScript-only portals:** the crawler escalates to a Playwright browser for
  heavily rendered pages (proven against NSW's Cloudflare-guarded portal). A
  portal that defeats even the browser fallback is **reported loudly to the
  user** — which strategies were tried, and that manual browser verification is
  needed — never silently skipped.
- **Bilingual documents:** non-English sections of mixed-language PDFs may be
  under-extracted. Our Thai Royal-Decree English translations are unofficial and
  pending Thai-reading legal review (the Thai text is verbatim from the official
  portal).
- **Delegated legislation:** primary statutes are retrieved; subordinate
  regulations are not *automatically* followed, though several subsidiary
  instruments (e.g. Singapore S 63/2021, Malaysia P.U.(A) 335) were discovered
  and banked via the NEW-law workflow.
- **Confidence calibration:** the `confidence` column is a *discovery*
  confidence, not a calibrated probability. Rows below **0.80** should be
  flagged for human review; final scoring authority stays with the human
  researcher (official Zone 3 guidance).
- **Sub-national instruments:** the VIC/NT/NSW state cross-border acts are
  banked as state-level evidence; whether sub-national law scores a
  national-level indicator is a methodology question pending expert input.
- **OCR engines:** only Tesseract + an OpenAI-vision fallback are wired today.

---

## Team

| Role | Name | Responsibility |
|---|---|---|
| Tech Lead & Architect | Dong | System framework, end-to-end workflow, legal–technical bridge |
| Legal Lead (Substantive) | Katie | RDTII regulatory logic, EN/ZH resolution, output QA |
| Full-Stack & AI | Chenming | Frontend, RAG pipeline, LLM + PostgreSQL integration |
| Backend | Abel | Extraction pipelines, anti-bot crawler |
| Project Coordinator | Rujing | Liaison, communications, documentation |

---

## License

Released under the **Apache License 2.0** per the hackathon requirements. See
[LICENSE](LICENSE).

## Key Dates

| Date | Milestone |
|---|---|
| **20 July 2026** | **Round 1 submission deadline** |
| 31 July 2026 | 20 teams shortlisted |
| 3 August 2026 | Live online pitching |
| 5 August 2026 | 5 finalists announced |
| October 2026 | Grand Finale — Bangkok |

---

*Disclaimer: outputs are for conceptual demonstration and research only, not
formal legal advice.*
