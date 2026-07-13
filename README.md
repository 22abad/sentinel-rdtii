# 🏛️ SENTINEL — AI Tool for Digital Trade Regulatory Analysis

> **"Where Code Meets Law."** Transforming ~100 pages of unstructured trade
> regulations into actionable, mapped data.

UN Global Hackathon on AI for Digital Trade Regulatory Analysis
Team: **SENTINEL** (Maynooth University) | Round: **1**
Last updated: **2026-07-11**

**Round 1 requirement:** the [Quick Start](#quick-start) below lets a reviewer
set up and run the tool. Mandatory scope: **RDTII 2.1 Pillar 6 (Cross-border
Data Flows)** and **Pillar 7 (Domestic Data Protection)**.

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

**Economies covered (Pillar 6 & 7, live-smoke verified):** Australia, Malaysia,
Singapore. Experimental discovery adapters also exist for China and Thailand.

---

## Quick Start

⚠ **Required for Round 1.** A reviewer with basic Python knowledge can run this
in a few minutes. The default provider below is a local open-weight model
(Ollama) so **no API key is required**; see [Swapping the LLM](#swapping-the-llm)
for cloud providers.

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

### 4. Run

```bash
python main.py --economy Singapore --pillar 6
```

**Output:** `outputs/Singapore_P6_<timestamp>.csv` and `.json`.

For a lower-cost first run that still exercises real discovery, document
retrieval, and mapping, process only the first accepted document:

```bash
python main.py --economy Singapore --pillar 6 --max-documents 1
```

> To try the pipeline with **no discovery or browser**, point at a local PDF
> instead: `--pdf path/to/law.pdf`. Mapping still uses the configured model.

---

## Full Usage

```bash
# Both pillars, restrict to specific indicators
python main.py --economy Malaysia --pillar all --indicators 7.3

# Bypass discovery and extract from a provided PDF
python main.py --economy Singapore --pillar 6 --pdf path/to/law.pdf

# Choose output format / directory / provider
python main.py --economy Australia --pillar 7 --format csv --output-dir outputs/ --provider deepseek

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
| `--provider` | Override `RDTII_LLM_PROVIDER` for this run |
| `--format` | `csv`, `json`, or `both` (default) |
| `--limit` | Maximum Discovery candidates returned per pillar (default: 20) |
| `--max-documents` | Stop after processing this many documents |
| `--registry-backend` | Source registry: `file` (CLI default) or `database` (full app) |

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

| | Live (default) | `--offline` | `--pdf <path>` |
|---|---|---|---|
| Retrieval | Playwright crawl + cache/Wayback fallback | Local law library | One provided file |
| Network needed | Yes | **No** | No |
| Mapping | Live pipeline | Live pipeline | Live pipeline |
| Discovery tag | NEW / KNOWN | KNOWN / cached NEW | per source |

---

## Discovering new laws (NEW vs KNOWN)

Beyond mapping the sample-kit laws, the tool rewards **independently finding
in-force Pillar 6/7 laws** the kit did not include. It decides novelty by
evidence, not by which crawler surfaced a result: a mapped provision is **KNOWN**
only if its statute is already in the authoritative baseline — the official
ESCAP RDTII Legal Inventory (`data/known_inventory.jsonl`, 195 laws across the
three economies) or the curated local law library; everything else is a genuine
**NEW** find.

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
| 4 | `last_amended` |  | Year of most recent amendment |
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
python scripts/evaluate_golden_set.py --mode offline --output reports/golden
```

The approved eight-case set currently reports 100% mapping precision, recall,
F1, citation exact-match, scoring, and scope accuracy in offline mode. This is a
small deterministic regression benchmark, not a claim of general model accuracy.

---

## Known Limitations

Transparency builds credibility — we are honest about the current state.

- **Model accuracy:** the un-fine-tuned open-weight model makes RDTII boundary
  errors (e.g. it may code a conditional-transfer clause as 6.1 instead of 6.4).
  Every mapping is therefore quote-verified and flagged for human legal review;
  a fine-tuned 12B model is in progress.
- **Golden-set coverage:** all eight current cases have substantive-lead sign-off,
  but they cover only five documents across AUS, MYS, and SGP. Broader legal
  review remains necessary before treating the benchmark as representative.
- **JavaScript-only portals:** the crawler falls back to OpenCLI for heavily
  rendered pages; some dynamic portals may still fail.
- **Bilingual documents:** non-English sections of mixed-language PDFs may be
  under-extracted.
- **Delegated legislation:** primary statutes are retrieved; subordinate
  regulations are not automatically followed.
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
