# OpenCode Handoff — SENTINEL (UN Digital Trade AI Mapper)

Team SENTINEL · UN ESCAP RDTII 2.1 Hackathon · Last updated: 2026-07-23

---

## What the tool does

An AI-powered regulatory mapping pipeline that, given an economy name and RDTII indicator, automatically:

1. **Discovers** relevant legislation from official government portals (crawling, downloading, OCR)
2. **Extracts** structured text from PDFs (including scanned/image-based ones)
3. **Maps** provisions to RDTII indicators via RAG (hybrid dense+lexical) + LLM classification
4. **Outputs** a 13-column evidence CSV + JSON per the official submission template

**Mandatory scope Round 1:** Pillar 6 (Cross-border Data Flows) + Pillar 7 (Domestic Data Protection) × SGP/MYS/AUS
**Round 2 expanded scope:** All 12 pillars × 7 economies (CHN, IND, IDN, LAO, MNG, RUS, THA — Round 1 SGP/MYS/AUS are not in Round 2)

---

## Project layout

```
.
├── main.py                  # Judges' CLI entrypoint (python main.py --economy X --pillar 6,7)
├── ai-service/              # Core pipeline (LLM, extraction, classification, validation)
├── crawler/                 # Web crawlers for official legal portals
├── pdf-reader/              # PDF parsing + OCR (PyMuPDF, Tesseract)
├── extract_sidecar/         # Sidecar service for extraction (OCR, table processing)
├── rdtii-frontend/          # React frontend (workbench UI, canvas, audit view)
├── rdtii-database/          # DB migrations + schema
├── tools/                   # 25 utility scripts (see below)
├── data/
│   ├── law_library/         # Seed laws with manifest (manifest.jsonl, 36 entries)
│   ├── known_corpus/        # Baseline law texts (Round 1 scope)
│   ├── round2_corpus/       # Baseline law texts (Round 2 scope, 12 pillars × 7 economies)
│   ├── round2_inventory.jsonl  # Official baseline law inventory for Round 2
│   └── seed_sources.jsonl   # Seed discovery sources
├── outputs/
│   ├── SUBMISSION_final/    # Round 1 final submission (94 rows, submitted July 20)
│   ├── SUBMISSION_Round1_SENTINEL.xlsx  # Round 1 xlsx artifact
│   ├── round2_final_v2/     # Best Round 2 submission (755 rows, 60.3% coverage)
│   └── ...                  # Many intermediate runs preserved
├── requirements/            # Official hackathon docs, templates, answer keys
├── docs/
│   ├── round2-engineering-log.md  # Every problem→fix story (1900+ lines)
│   ├── round2-meeting-report.md   # Auto-generated coverage numbers
│   └── round2_gap_worklist.csv    # 91 remaining uncovered cells
└── .env                     # API keys + provider config (active: Ollama qwen2.5:14b)
```

---

## Current state at a glance

### Round 1 — SUBMITTED (July 20 deadline)
- **94-row artifact**, 16/16 official non-zero economy×indicator cells covered
- 3 economies (SGP/MYS/AUS), Pillars 6+7 only
- 94/94 verbatim independently verified against re-fetched official sources
- Judge reproducibility confirmed (fresh venv + key-free Ollama qwen2.5:14b → REPRODUCIBLE)
- Artifact: `outputs/SUBMISSION_final/` + `outputs/SUBMISSION_Round1_SENTINEL.xlsx`

### Round 2 — IN PROGRESS
- **12 pillars × 7 economies** (CHN, IND, IDN, LAO, MNG, RUS, THA)
- **Current best: `outputs/round2_final_v2/` — 755 rows, 213 laws, 60.3% cell coverage**
- 138/229 official non-zero cells covered
- 96.2% verbatim grounding rate
- 755 tests green
- Cost: $12.96 for full submission on deepseek-v4-flash, $0 on Ollama

### Remaining gap: 91 uncovered cells (`docs/round2_gap_worklist.csv`)

| Root cause | Count | Meaning |
|---|---|---|
| `FETCH_GAP` | 30 | Law not yet downloaded locally |
| `CORPUS_QUALITY` | 18 | Downloaded but text is wrong/short/corrupt |
| `EXTRACTION` | 43 | Text present but extraction not surfacing the provision |

**Corpus quality is largely solved** (84% real statute after the `refetch_statutes.py` run). The biggest lever now is extraction/classification recall.

---

## How to run

### Quick start (judge path — key-free, <10 min)
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Defaults to Ollama qwen2.5:14b + free DuckDuckGo search
python main.py --economy Singapore --pillar 6
# Output: outputs/Singapore_P6_<timestamp>.csv + .json
```

### Round 2: from pre-fetched corpus (fast, offline)
```bash
python main.py --economy China --from-corpus --pillar all --provider deepseek
```

### Round 2: live discovery (crawls + maps from scratch)
```bash
python main.py --economy China --pillar all --provider deepseek
```

### Provider options
- `--provider deepseek` — DeepSeek v4 Flash (fast, cheap, needs DEEPSEEK_API_KEY)
- `--provider ollama` — Local Ollama (free, key-free, default for judges)
- Also supports: openai, claude, gemini, groq

### Key tools
```bash
python tools/coverage_report.py --gaps              # Coverage analysis
python tools/refetch_statutes.py                      # Re-fetch missing statutes
python tools/build_round2_corpus.py                   # Build corpus from inventory
python tools/cost_report.py                           # Cost breakdown
python tools/content_smoke.py                         # Quick sanity check
pytest tests/                                         # Full test suite (755 tests)
```

---

## Architecture deep-dive

### Pipeline stages
1. **Crawler** (`crawler/`, `ai-service/crawler.py`) — navigates official portals, retrieves PDF URLs
2. **PDF Reader** (`pdf-reader/`, `extract_sidecar/`) — downloads + OCR + structural parsing
3. **Ingest** — chunks text, generates embeddings (MiniLM), builds tsvector index
4. **Retrieval** (`ai-service/chunker.py`, hybrid search) — RRF fusion of dense cosine + lexical ts_rank_cd
5. **LLM Mapping** (`ai-service/main.py`, `ai-service/classifier.py`) — maps provisions to indicators
6. **Validation** (`ai-service/validation.py`, eligibility gates) — verbatim grounding, statute-word checks, scope classification
7. **Output** — 13-column CSV (Title Case headers) + JSON

### Key design decisions
- **Hybrid search**: dense (MiniLM cosine) + lexical (PostgreSQL tsvector, 'simple' config for multi-language) fused via RRF
- **No vendor lock-in**: LLM provider is a single env var (`RDTII_LLM_PROVIDER`), abstracted in `ai-service/` provider classes
- **Flag mode**: `RDTII_ELIGIBILITY_MODE=flag` keeps ineligible mappings flagged for human review (default since PR #300)
- **Self-title correction**: The pipeline derives a law's real name from its own text head to catch hallucinated names (#309)
- **Table reconstruction**: PyMuPDF `find_tables()` reconstructs ruled schedules as Markdown tables so numbers aren't lost

---

## Critical rules (from CLAUDE.md — read FIRST before any work)

### Ground truth
1. **Official answer key is ground truth.** Scores/mappings/rules come from `requirements/Hackthon Knowledge Products/` — the Round-1/2 Database xlsx (methodology sheet = criteria + allowed scores; economy sheets = the answer key with Coverage annotations), the framework PDFs, the submission templates. **Trust the official answer key over any external research.**
2. **When unsure, read `requirements/` FIRST.** Never guess, never punt to Dong.
3. **No scoring hallucination.** Every indicator score is a value the official methodology defines for THAT indicator — no fabricated tiers.
4. **Verify before presenting.** Independently confirm a law/status/indicator/score exists before showing or claiming it.

### Process
5. **pytest green before `gh pr merge`.** Update exact-set/count tests in the SAME commit as a new law/seed. All work via PR + squash-merge.
6. **Record everything.** Problem→fix stories to `docs/round2-engineering-log.md` AND Dong's Obsidian vault.
7. **Proactively Telegram Dong** on decisions/intervention, major milestones, or unfixable errors.

### Submission format
8. **Round 1 submits EVIDENCE ROWS, not scores.** The 13-column CSV (law → indicator → verbatim). Judges compute scores.
9. **CSV header = official Title Case** (`Economy, Law Name, ...`) per `OUTPUT_TEMPLATE_31MAY.xlsx`, plain UTF-8 no BOM.
10. **Coverage = 27/27** official economy×indicator cells have curated seeds (Round 1 scope).

### Indicator meanings — authoritative (template sheet is WRONG)
- ⚠️ `OUTPUT_TEMPLATE_31MAY.xlsx` has an **"Indicator Reference" sheet that is misleading**. Trust the Round 1 Database methodology / RDTII 2.1 framework instead.
- **6.1** Ban and local processing · **6.2** Local storage · **6.3** Infrastructure requirement · **6.4** CONDITIONAL cross-border transfer · **6.5** non-regulatory
- **7.1** framework existence · **7.2** dedicated cybersecurity framework · **7.3** data retention (needs SPECIFIC minimum period) · **7.4** DPO/accountability · **7.5** government access (court order → 0)

---

## Key files to read before starting

| File | Why |
|---|---|
| `CLAUDE.md` | Full project rules (the above is a summary) |
| `docs/round2-meeting-report.md` | Auto-generated coverage numbers, per-economy breakdown |
| `docs/round2-engineering-log.md` | Every problem→fix story (1900 lines — search for your issue before debugging) |
| `docs/round2_gap_worklist.csv` | The 91 remaining uncovered cells |
| `requirements/README_template.md` | The submission README template judges will follow |
| `requirements/Hackthon Knowledge Products/` | Official answer key (xlsx with methodology + economy sheets, framework PDFs) |
| `data/round2_inventory.jsonl` | Every baseline law the tool knows about |

---

## Suggested prompts for OpenCode

### Prompt 1: Understand the codebase
```
Read CLAUDE.md and docs/round2-engineering-log.md (the last 200 lines for recent context). 
Then read docs/round2-meeting-report.md and docs/round2_gap_worklist.csv.
Summarize the current state: what's done, what's remaining, and the top 3 things to work on next.
```

### Prompt 2: Attack the FETCH_GAP cells
```
Read docs/round2_gap_worklist.csv and filter for FETCH_GAP rows.
For each row, we need to find and download the official statute from the economy's 
government legal portal. The inventory is in data/round2_inventory.jsonl.

For each FETCH_GAP cell:
1. Find the corresponding law in data/round2_inventory.jsonl
2. Try to fetch it using the crawler (crawler/) or tools/refetch_statutes.py
3. If the URL is dead/blocked, note it and move on
4. Store the fetched PDF/text in data/round2_corpus/
5. Update docs/round2_gap_worklist.csv to reclassify the cell

Run: python tools/coverage_report.py --gaps after each batch to measure progress.
```

### Prompt 3: Attack the EXTRACTION cells
```
Read docs/round2_gap_worklist.csv and filter for EXTRACTION rows.
These are cells where the corpus text EXISTS locally but extraction isn't surfacing 
the right provision. For each:

1. Check what law text we have (data/round2_corpus/)
2. Check what the indicator is looking for (requirements/Hackthon Knowledge Products/ 
   methodology sheet)
3. Run a targeted extraction for that specific law+indicator pair
4. Debug the extraction pipeline — is it a chunking issue? A classification issue? 
   A language issue (non-English text)?
5. See docs/round2-engineering-log.md for known extraction failure patterns

Key extraction gates to be aware of (these silently drop rows):
- is_section_header (context-aware, rejects headings)
- Weak-evidence fragment (<45 chars)
- Citation-style quote (opens with section citation + dash/colon)
- No statute word (Malay/English legal vocabulary required)
- Operative language (must have an operative verb)
- Self-title mismatch (law name derived from text head vs manifest name)
```

### Prompt 4: Attack the CORPUS_QUALITY cells
```
Read docs/round2_gap_worklist.csv and filter for CORPUS_QUALITY rows.
These are cells where we have a file but the text is wrong/short/corrupt.

Common causes (see round2-engineering-log.md):
- Wrong law was downloaded (IDN had 34 files silently overwritten — 
  tools/restore_corpus.py recovered 13)
- JS-only portal returned a stub page instead of the PDF
- PDF is image-only and OCR failed

For each cell:
1. Check the file's sha256 and char_count against the expected values
2. Re-fetch from the official URL if corrupted
3. If OCR is the issue, try a different OCR engine or pre-processing
```

### Prompt 5: Fill in the submission README
```
Read requirements/README_template.md. Fill in all placeholders with actual values from the project:
- Tool Name: SENTINEL
- Team Name: Team SENTINEL
- Economies covered: Singapore, Malaysia, Australia (Round 1); China, India, Indonesia, 
  Lao PDR, Mongolia, Russian Federation, Thailand (Round 2)
- Repo URL: [the actual repo URL]
- Cost numbers: run tools/cost_report.py to get measured costs
- Known limitations: see docs/round2-engineering-log.md for honest caveats
- Test suite: 755 tests

Do NOT fabricate any numbers — run the actual measurement tools.
```

### Prompt 6: General improvement
```
We need to improve cell coverage from 60.3% to as high as possible.
The gap worklist is at docs/round2_gap_worklist.csv (91 cells remaining).

Working cell by cell:
1. Pick an uncovered cell
2. Check if the law is in data/round2_inventory.jsonl
3. If not fetched: fetch it via crawler or manual download
4. If fetched but bad text: re-fetch or re-OCR
5. If text is good but no evidence: debug extraction for that specific law+indicator
6. Run coverage_report.py after each fix to confirm the cell is now covered
7. Update the gap worklist

Always verify: any new evidence row must have its verbatim snippet confirmed 
against the source text. No fabrication.
```

---

## Major pitfalls we've already hit (search round2-engineering-log.md for details)

1. **Name-vs-source hallucination** — rows quote the right text but name the WRONG law. Fixed with self-title derivation (#309).
2. **Silent row drops** — eligibility gates dropped rows with no warning. Fixed with prepare-time repair loop (#301, #302, #306).
3. **Corpus corruption** — 34 IDN files overwritten with wrong-law text. Fixed with sha256/char_count audit + restore.
4. **Table data lost** — ruled schedules arrived as unlabelled number runs. Fixed with `find_tables()` Markdown reconstruction.
5. **Lexical retrieval blind spot** — "section 46" never returned the actual s46 text. Fixed with hybrid RRF fusion.
6. **Cache replay broke quote-highlight** — cached runs didn't emit `started` events. Fixed by replaying all events.
7. **Bare judge run produced 0 rows** — formal-output filter was undoing flag mode. Fixed in PR #300.
8. **Template's Indicator Reference sheet is WRONG** — trust the Round 1 Database methodology, not the template's reference sheet.
9. **7.3 = 0 unless a specific minimum retention period is stated** — "as long as necessary" = 0.
10. **7.5 scores 1 only for access WITHOUT a court order** — warrant/magistrate order → 0.

---

## Quick reference: running things

```bash
# Full test suite
pytest tests/ -x

# Coverage report
python tools/coverage_report.py --gaps

# Generate submission for one economy (from corpus, fast)
python main.py --economy China --from-corpus --pillar all --provider deepseek

# Content smoke test
python tools/content_smoke.py

# Cost report
python tools/cost_report.py

# Rebuild corpus from inventory
python tools/build_round2_corpus.py

# Re-fetch missing statutes
python tools/refetch_statutes.py
```

---

## Environment

- **Active LLM provider:** Ollama (`qwen2.5:14b` on `localhost:11434`)
- **Database:** PostgreSQL (see `.env` for connection string — port 5433 locally)
- **Python:** 3.10+
- **Node:** For frontend only (`rdtii-frontend/`)
- **DeepSeek API key** is in `.env` (for fast batch runs)
- **Platform:** macOS (darwin)
