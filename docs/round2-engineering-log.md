# Round 2 engineering log — problems met, root causes, fixes

_Companion to `docs/round2-meeting-report.md` (the numbers). This is the story
behind them: every material problem hit while standing up the 12-pillar ×
7-economy pipeline, its root cause, the fix, and the verification. PR numbers
link every claim to code._

---

## 📌 CURRENT STATE SNAPSHOT (2026-07-19) — read this first after a long session

**LATE-NIGHT UPDATE (2026-07-19, PRs #345–#347).**
- **#346 — quote-highlight went dead the moment a document became a cache
  hit.** Classic audit click stopped jumping/highlighting the source panel.
  Root cause: the extraction-cache replay path (#339) re-emitted `mapping`
  events but never the `started` event that carries `source_text` — so on a
  cache hit the panel text stayed empty and the highlight view had nothing to
  render into. Fixed on both sides (replay now emits `started`; frontend also
  backfills from `node_output`), plus SourceView now treats quote offsets as
  a hint and relocates the verbatim by exact/whitespace-tolerant search.
  **Lesson: a cache replay must be indistinguishable from a real run — audit
  every event the live path emits, not just the payload rows.** Verified via
  Playwright (cached Pekeliling URL → click deep row → mark scrolled into
  viewport; second click moves the highlight).
- **#347 — Google Custom Search backend.** DDG (free default) bot-challenges
  after rapid searches. Added Google's official CSE JSON API (100/day free,
  own key, ToS-clean) as `DISCOVERY_SEARCH_BACKEND=google` / auto-selected on
  GOOGLE_CSE_KEY+GOOGLE_CSE_ID; same process-wide breaker as SerpApi. Judge
  default unchanged (key-less DDG). Bing is NOT an option (Microsoft retired
  the Bing Search APIs in Aug 2025); China discovery stays search-engine-free
  via the china_flk direct portal adapter.
- **#345 — demo prep.** New primary OCR asset: 300dpi image-only scan of the
  Malay Pekeliling (5 article-level P7-I4 rows, correct bilingual name).
  Found in the process: the old PDPA-excerpt scan misattributes itself to
  "Private Healthcare Facilities and Services Act" — the #342 self-title
  fallback latches onto any Act named in the first 1500 chars when an excerpt
  has no title page (OPEN ITEM; asset quarantined with a warning in
  demo-assets/README). Dossier staleness now shows worst-severity reasons
  with an N/M row count instead of a cross-row union ("repealed"+"draft" had
  landed on one in-force Act).

**EVENING UPDATE (2026-07-19, PR #343) — document dossier + canvas no-overlap.**
- *Problem (Dong, from the live UI):* the same document showed a DIFFERENT
  source grade / timeframe / release year / staleness on every mapping card —
  "幻觉实锤或逻辑错误". Root cause was architectural, not hallucination: doc-level
  attributes were rendered per mapping from per-chunk LLM fields, and
  `ReasoningReport` fired per-card `verifyReleaseYear`/`verifyTimestamp` API
  calls, so N cards = N independent (noisy) resolutions of one document.
- *Fix:* `DocumentDossier` — document identity consolidated ONCE above the
  triage chips: best-confidence source grade, modal timeframe, worst staleness
  (union reasons), ONE release-year/timestamp probe per document; grouped only
  by deterministic identity (URL/SHA — grouping by LLM `source_legislation`
  would have re-split one doc into "several"). Live-updating while streaming.
  Per-card report keeps only score/flags/provision/scoring-inputs (staleness
  keys no longer leak into Scoring inputs).
- *Row titles:* "P7.2 · <per-chunk law-name variant>" × N said nothing — now
  `clause · "verbatim snippet"`. Shared components ⇒ classic/canvas in sync.
- *Canvas:* hard no-overlap invariant (drag stop / drop / spawn / resize /
  content growth all funnel into a push-apart resolver; changed node stays
  put). **Trap worth remembering:** on controlled React Flow, `getNodes()`
  items often lack `measured` — the resolver first separated against a 560px
  fallback while the card was really 644px, leaving a real 42×52 overlap; DOM
  `offsetWidth/Height` (layout units, zoom-independent) is the ground truth.
  Plus an always-visible drag strip pinned above each panel's scroll container.
- *Verified* via Playwright UI-driving: 0 overlaps across 4 scenarios; dossier
  = 1 per document, 6 mappings consolidated; classic parity. 655 tests green.

**MORNING UPDATE (2026-07-19): Dong decided — flag mode IS the default.** Executed:
- **PR #300**: `RDTII_ELIGIBILITY_MODE` default `reject` → `flag` (reject is the
  opt-in). Critical companion fix found by empirical test: the formal-output
  filter (`filter_formal_submission_rows`) was silently undoing flag mode — a
  bare judge run (`--offline`, no `--include-review`) produced **0 rows** because
  every flagged row was excluded at the output boundary. In flag mode the filter
  now keeps flagged rows, annotated in Notes for the official 20% human-validation
  step. `--include-review` is only meaningful under `reject` now.
- **PR #301**: the MYS 6.2 seed regression is DIAGNOSED and FIXED (it was not
  "deep #293 classifier damage"; classifier is bypassed for hinted seeds). Two
  stacked gates killed it: (1) `is_section_header` called the extractor's 3-word
  verbatim "kept in Malaysia" a *heading* — now context-aware: a verb-less span
  continuing into more provision text on the same line is a list-limb fragment,
  not a marginal note (hard heading patterns unchanged); (2) after that, the row
  died *silently* at submission validation as a <45-char weak-evidence fragment —
  that predicate now also runs at prepare time so the repair loop asks the model
  for the complete limb. Verified live: repair expands the quote to the full
  s24(2)(c) limb and `--economy Malaysia --pillar 6 --offline` emits P6-I2 again,
  score 0.5 (= official key). NOTE: the ITA s82 seed excerpt is retention-only
  (no local-storage clause), so it honestly yields no 6.2 row — Service Tax
  s24(2)(c) carries MYS 6.2 coverage.
- **PR #302**: run5 (the first fresh finalization run) exposed the third
  silent-drop class — the AUS Cyber Security Act 2024 seed's 7.2 verbatim was
  the excerpt's descriptive header line, dropped by the #297 nonsubstantive
  gate, leaving the official-nonzero AUS 7.2 cell uncovered. Same medicine as
  #301: the nonsubstantive/citation-style predicates now run at prepare time so
  the repair loop swaps in the operative clause (verified live: s3 Objects
  text). P7-I1 keeps its bare-title exemption (golden set; the eval-runner test
  caught the first over-broad version).
- **FINALIZED (run6, 2026-07-19 ~07:50)**: fresh 3-economy live run with the
  bare judge command (zero env vars / zero flags) → **64 rows, ALL 16 official
  non-zero economy×indicator cells covered** (AUS 39 / MYS 14 / SGP 11; extras
  on zero-score cells 7.1/7.2 are flagged evidence, judges decide). Submission
  cleaning dropped **0 rows** (64→64) — the quality gates now run inside the
  pipeline, so the tool's raw output is submission-clean. Rebuilt
  `outputs/SUBMISSION_final/` + `outputs/SUBMISSION_Round1_SENTINEL.xlsx`
  (3-sheet official template, 64 rows, no BOM, 0 empty rationale/URL). The
  night's v3 artifact is preserved at `outputs/SUBMISSION_final_v3_backup/`.
  Acceptance basis: official Round 1 Database answer key — non-zero cells are
  SGP {6.2,6.4,7.3,7.4,7.5}, MYS {6.2,6.4,7.3,7.4,7.5},
  AUS {6.1,6.2,6.4,7.2,7.3,7.5} (SGP 6.1/7.1 are officially 0, so run5/run6
  "missing" them vs v3 was correct — v3's six FSMA 6.1 rows were the off-topic
  kind the grader removes).
- **Independent verbatim audit COMPLETE (run6, ~09:30)**: every official source
  re-fetched (0 unfetchable), all 64 rows byte-compared. **One mismatch** — an
  AUS P7-I1 NSW PPIP row whose verbatim was the constructed heading "Section
  19(2) — Special restrictions on disclosure of personal information
  (cross-border):" (slipped every gate: no statute word, no operative verb, >8
  words, not bracket-terminated). Row dropped (it sat on the officially-zero
  AUS 7.1 cell — zero coverage cost) and the gate hardened (**PR #306**: a
  quote OPENING with a section citation + dash/colon separator is
  citation-style, caught at prepare time).
- **FINAL SUBMISSION STATE: 63 rows (AUS 38 / MYS 14 / SGP 11), 63/63
  independently verbatim-confirmed against re-fetched official sources, 0
  unfetchable, 16/16 official non-zero cells covered, 0 empty rationale/URL,
  no BOM.** `outputs/SUBMISSION_final/` + `outputs/SUBMISSION_Round1_SENTINEL.xlsx`.
- 649 tests green, main at #306.
- **Demo-confirmation run (run7, ~10:20, pre-recording)**: one more fresh bare
  3-economy live run → 69 rows (AUS 44 / MYS 14 / SGP 11), 16/16 official
  non-zero cells, hygiene clean, **and the full independent verbatim audit came
  back 69/69 confirmed, 0 mismatch, 0 unfetchable** — the first fresh run whose
  RAW output passes the independent audit 100%. The three prepare-time quote
  gates (#301/#302/#306) are closed-loop; post-hoc cleaning is no longer doing
  any work. Dong recording the demo against this state.
- **Name-vs-source hallucination class found via Dong's own fresh run (~11:00,
  PR #309)**: rows quoting the Identity Verification Services Act 2023 shipped
  as "Privacy Act 1988", and Pasture Seeds Levy Collection Agreement gazette
  notices shipped as "Privacy Act 1988 (Cth)" / "SA GIPP Instruction (PC012)".
  The verbatim audit CANNOT catch this — quote ∈ URL text holds; the NAME is
  wrong (the model names the act a provision talks ABOUT; the search-result
  candidate title can be equally wrong; the per-URL majority vote then locks
  the wrong name in). **9 such rows excised from the finalized artifact →
  FINAL: 54 rows (AUS 29 / MYS 14 / SGP 11), 16/16 official non-zero cells
  intact, every remaining row independently verbatim-verified.** Root fix:
  `build_row` derives the document's own opening title from the fetched text
  head; near-zero token overlap or disjoint years → the self-title wins, with
  a Notes annotation (seeds keep their authoritative manifest name); renamed
  Collection-Agreement rows then die at the no-statute-word gate. 650 tests.
- **Judging requirements re-read (official Q&A + README template)**: judges do
  NOT run our dev command — they follow the README Quick Start in a fresh venv
  (default = key-free Ollama qwen2.5:14b + free DuckDuckGo), <10 min. Stage 2
  rubric: Substantive accuracy 40% / Technical resilience 30% / Architecture
  30% + 20 pts Discovery of New Evidence; LLM swappability heavily scored;
  tool requirements: open-source, modular, OCR <5% CER, audit view,
  self-hostable; expectation 5–10 documents across the 3 economies. Known open
  items: local machine only had qwen2.5:32b (pulling 14b + running
  `tools/check_reproducibility.sh` = the true judge path); one empty-rationale
  row appeared in Dong's live run (P7-I1 My Health Records — one-off, gate TBD).
- **OVERNIGHT FINALIZATION (2026-07-19 night): 94-row artifact, everything
  green.** Afternoon/evening closed 14 more PRs (#312–#337): workbench UI
  session found and fixed the extent-keyword misfire, the "cyber security"
  open-compound classifier gap, runtime law-name correction, canvas
  Extract→Audit auto-wiring + one-click file pipeline (prepare-not-bill,
  auto country detect, auto ingest), cascade delete, chain-raise, Tidy,
  Documents inline sign-in + live refresh, RAG scoped retrieval +
  heading-noise demotion, streaming flag-not-drop PARITY (the workbench path
  still had #293's hard drop!), stream terminal status, and full **Malay
  legal-vocabulary support across every gate** (classifier, statute-word,
  operative-language ×4 copies, self-title, eligibility DPO) — Malay was the
  one Round-1 language the gates didn't speak. Overnight full bare batch run:
  **94 rows (AUS 38 / MYS 22 / SGP 34), 16/16 official non-zero cells, 0
  empty fields, 0 name-vs-URL mislabels, 7 Malay-verbatim Pekeliling rows
  under their true instrument name, submission cleaning 0 drops, and 94/94
  independently verbatim-verified (0 unfetchable)**. content_smoke 4/4.
  Artifact promoted: `outputs/SUBMISSION_final/` + xlsx = 94 rows; prior
  54-row artifact kept at `outputs/SUBMISSION_final_v4_backup/`. 655 tests,
  main at #337.
- **Dong's independent re-run (dong_run2, ~11:16) passed all four checks**:
  62 rows (AUS 37 / MYS 14 / SGP 11), 16/16 cells, 0 empty fields, **0
  name-vs-URL mislabels (5 rows carry "law name corrected" notes — #309
  correcting live), 62/62 independent verbatim audit, 0 unfetchable**. The
  Pasture Seeds Levy Agreements now surface under their true names and die at
  the no-statute-word gate, visible in the run log itself. Row-count stability
  across four fresh runs: 64 / 69 / 65 / 62 (±10% live-discovery variance by
  design; seed backbone and cell coverage constant). Judge-path
  reproducibility gate also green (fresh venv + pip install + key-free Ollama
  qwen2.5:14b → REPRODUCIBLE).

**NIGHT UPDATE (for Dong, ~08:00):** PR #293 (`codex/mapping-precision-gate`)
added a precision-first eligibility gate that hard-drops any mapping failing
strict feature/pattern + LLM-verifier checks — it decimated the submission
(SGP 66→4), failing coverage + the 20-pt discovery, and since judges RUN the
tool a 4-row pipeline is a broken submission. Feature names match, so it's
intended (not a trivial bug), just far too aggressive. **Fix (#295, opt-in):
`RDTII_ELIGIBILITY_MODE=flag` keeps ineligible mappings and FLAGS them for human
review instead of dropping — default (`reject`) byte-identical, 642 tests green.**
The submission is generated with `RDTII_ELIGIBILITY_MODE=flag … --include-review`
(+ `RDTII_ELIGIBILITY_VERIFIER=0` for speed, since the verifier's verdict only
matters as a drop signal, which flag mode ignores). **DECISION FOR DONG:** make
flag mode the default (recall + human-in-the-loop) vs #293's precision-first
default — this is a design-philosophy call on your account's code, so I did NOT
change the default, only added the opt-in.
Fallback if the live flag-mode run is unsatisfactory: `outputs/SUBMISSION_final/`
(v3-based, 66 rows, flags) + `outputs/SUBMISSION_Round1_SENTINEL.xlsx`.

**Second #293 symptom found (night):** the MYS 6.2 tax seeds (ITA s82 #286,
Service Tax s24 #287) no longer produce a P6-I2 row even offline in flag mode —
they are extracted but their 6.2 mapping is gone. Pre-#293 they worked (verified
at seed time). So #293's classifier.py / feature-spec changes (not just its drop
gate) also regressed seed extraction. Not chased further tonight (deep, and the
right fix depends on the #293 design decision). **The submission is unaffected:**
the v3-based `SUBMISSION_final` (built pre-#293) has the MYS 6.2 row and full 8/8
indicator coverage. Recommendation for Dong: treat #293 as over-aggressive across
the board (drops recall AND regresses seed mappings); either tune it down to
flag-only or revert the classifier/feature parts, keeping the eligibility signal.
Chosen submission artifact = the v3-based file; live flag-mode proves the tool
runs end-to-end (67 rows) but its per-run coverage varies (live variability).

**Scoring/coverage now aligned to the official answer key. 626 tests green, main clean.**
- **Coverage: 27/27** official economy×indicator cells have a seed hinted for them (library = 33 entries). Only gap was SGP 7.4 → closed by banking PDPA s11(3) DPO (#278).
- **Scoring fixes (all verified vs the official answer key):** consent-gate veto for 7.5 (#259), 0.25 fabricated-tier removed + official-value guard (#260), 7.5 coverage top-up via hinted seeds (#261), judicial-warrant → 7.5=0 (#265), government-data exclusion scoped to 6.1-6.4+7.3 (#266→#276), non-regulatory indicators (incl. 6.5) drop law-derived rows (#268), **6.1/6.2 sector-specific personal = 0.5, horizontal = 1** (#276). Deterministic alignment test `test_official_score_alignment.py` pins scorers to the key.
- **Submission format:** CSV header is official Title Case (#275). `chunker.reflow` preserves inline amendment markers so verbatim matches the source (#277).
- **Latest 3-economy runs (DeepSeek, seed+live):** MYS 21 rows, SGP 26 rows (0 hallucination) — all official non-zero indicators covered. AUS run in progress at time of writing.
- **Known reviewable item:** a weak Banking Act NEW row on SGP 7.4 (title-as-quote) — flag for human review, not a blocker.
- **Insight worth remembering:** internal scores are NOT submitted (evidence rows are); score variance across runs is LLM feature-extraction noise, not a scoring-logic bug (logic is proven by the alignment test).

---

## 2026-07-18 (night) — final re-run blocked by PR #293 eligibility gate

The final end-to-end re-run (run4, all gates + flags native) collapsed: SGP
66→4 rows, MYS/AUS similar, "No formally submittable mappings remained after
eligibility and human-review filtering." Diagnosed:
- NOT a provider issue (DeepSeek responds; documents extract).
- NOT the human-review filter (persisted with `--include-review --allow-empty`).
- **Root cause: PR #293 `codex/mapping-precision-gate` (commit 5c091e7, "Improve
  mapping precision and eligibility validation", authored dong@22abad.com /
  IrishDevNoob, merged ~21:21)** — a new 289-line deterministic eligibility gate
  (`ai-service/agents/eligibility.py`) that rejects any mapping whose quote does
  not hit its strict deterministic evidence-span patterns. Far too aggressive:
  it decimates recall ("Pillar 6: 2 provisions mapped from 4 documents").
- v3 was produced BEFORE #293; that is why v3 (66 rows) is healthy and run4 is not.
- NOT reverted — the change is on Dong's account and looks intentional
  (precision-first). Flagged to Dong for a tune-or-revert decision.

**Fallback submission is intact and ready:** `outputs/SUBMISSION_final/` (66 rows —
SGP 20 / MYS 14 / AUS 32, 29 NEW, MYS 6.2 covered, 15 rows flagged for human
review incl. the 6 FSMA→6.1 mis-maps) + `outputs/SUBMISSION_Round1_SENTINEL.xlsx`
(official 3-sheet template, no BOM). Built by re-validating v3 through the
current validator (deterministic flags only) — the eligibility gate lives in the
extraction path, not the validator, so it did not touch this artifact.

## 2026-07-18 — row-by-row verification, mapping-gate, stable+effective re-run

Live re-run of the three economies → independent row-by-row verification → clean
submission `outputs/final_submission_20260718_v2/` (SGP 12, MYS 14, AUS 32 = 58).

- **Verbatim integrity: 33/33 NEW quotes** independently re-fetched from source and
  confirmed as exact substrings — 0 fabricated. Structural: 0 conf-0.00, 0 empty
  rationale, all official gov domains, 0 URL-reuse flags, no BOM (Title-Case).
- **Mapping-layer mis-maps found (real quote, wrong indicator)** — the verbatim
  gate cannot catch these because the quote is genuine: SGP Strategic Goods
  (Control) Act → 6.x (export-control-of-goods), SGP Payment Services → 6.1
  (e-money rules), SGP PDPA → 7.2 (quote from an un-enacted Draft Bill), AUS
  Identity Verification Services Act conf-0.40 cluster (law-name/rationale
  mismatch). Fixed by the mapping gate (#285): four rules — export-control
  domain, payment-law-off-localization, draft-bill verbatim, rationale/law-name
  subject mismatch.
- **Coverage vs the official answer key:** the "missing" cells are correct
  absences — SGP/MYS/AUS 6.3 = 0 (no infrastructure requirement), SGP 6.1 = 0,
  SGP/MYS 7.2 = 0. MYS 6.2 = 0.5 WAS a real gap (ITA 1967 s82) → seeded (#286).
- **Re-run comparison (run1 raw vs run2 gate-tightened): STABLE + EFFECTIVE.**
  Counts SGP 19→12, MYS 13→13, AUS 40→32. AUS NEW families 11/11 present in BOTH
  runs (discovery is consistent on substance; only marginal rows vary — the
  hallmark of real live discovery, not a canned list). Mis-maps: SGP 7→0, AUS
  IVS 8→1 (the 1 remaining is the GOOD conf-1.00 s10→7.3 row). run2 needs zero
  manual cleanup — the gate auto-produces what was hand-cleaned from run1.
  Deterministic core still reproducible; DeepSeek temp=0 verified byte-stable.

## 2026-07-18 — "fresh run ≠ FINAL" investigation + reproducibility architecture

Dong ran the three economies with `--offline` and got fewer rows than the curated
`outputs/final_submission_20260718_FINAL/` (SGP 11 vs 23, AUS 22 vs 40, MYS 7 vs
14) and asked why — judges will re-run the tool, so a hand-curated FINAL they
can't reproduce is worthless. Full diagnosis:

- **The tool IS deterministic.** Two `--offline` MYS runs produced byte-identical
  row sets (same 7 rows, same drops). DeepSeek at `temperature=0` is stable here
  (the extraction path `_call_llm` uses `temperature=0`; only the generic
  `query()` uses 0.3 and is not on the verbatim path). So the gap is NOT run
  variance — no extraction cache needed.
- **`--offline` is a thin-seed SUBSET, not the intended submission mode.** The
  banked seeds are single-section excerpts (e.g. My Health Records seed = only
  s77, 1471 B; COVID-app seed = only s94F, 877 B). FINAL's rich rows (My Health
  s17/s69, COVID s94K/94ZC, NSW s40) came from **live full-text fetch**, never
  banked — so `--offline` structurally cannot produce them.
- **The DEFAULT (seed + live) run over-reproduces FINAL.** `python main.py
  --economy Australia --pillar 6,7` → **Seed 99 + Live-discovered 134 → 44 clean
  rows, NEW=20, all 8 indicators** (vs FINAL 40/NEW19, vs offline 22). Live crawl
  is what judges actually run and what the 30% Technical-Resilience + 20-pt
  Discovery scores reward. So the "judges can't reproduce it" worry dissolves:
  in the mode judges use, the tool produces MORE than FINAL.
- **Reproducibility architecture (locked in, per Dong):** `--offline` seed pass =
  deterministic, byte-reproducible KNOWN backbone (27/27 official cells). Live =
  genuine on-the-spot NEW discovery, variable by nature — and that variability is
  the *proof it's real discovery, not a hardcoded list*. Official Q&A never
  requires live output to be byte-identical ("repeatably" = the capability works
  on unseen jurisdictions, not identical bytes). Corollary: do NOT bake NEW
  discoveries into offline seeds to force reproducibility — that would be the
  FAIL anti-pattern (hardcoded discovery). Judges audit each NEW row by verbatim
  vs Source URL, not by re-run diffing.
- **Scope check vs official Q&A (April 28 2026):** Round 1 is P6+P7 only
  ("non-negotiable"); P11 is NOT a scored pillar (scaling to more pillars is only
  an architecture *bonus*). Discovery of New Evidence = **20 pts at Stage 2** but
  must be P6/P7-relevant. ⇒ **Cyber Security Act 2024 dropped from the P7 rows**:
  its true home is 11.1 (its own manifest note says 7.2 is not auto-produced),
  mislabelling it 7.2 would cost Substantive-Accuracy points; it survives only as
  a demo talking point ("our engine even finds cross-pillar P11 laws").

**Quality gate (#284): drop zero-confidence rows at final assembly.** The FINAL's
garbage (a *Pasture Seeds Levy Agreement* contract clause mapped to 7.3, circular
"has the meaning given under the Privacy Act" definitions, "entities should be
mindful" guidance notes) was hand-assembled — a fresh **offline** run emits none
of it (0 conf-0.00, 0 empty-rationale across SGP/AUS/MYS). But a **live** run
surfaces ~5 such rows (marginal SA-admin instruments the extractor honestly
scores 0.00). Fix: new `drop_zero_confidence_rows()` applied in `main.py` AFTER
`validate_submission_rows` (kept OUT of the validator itself — its unit fixtures
leave `confidence` at the 0.0 default, so a floor there dropped 13 legit
fixtures). Live AUS 44 → 39, dropping exactly the 5 noise rows, all 20 NEW laws
kept. A UTF-8-BOM-removal for the CSV header is a separate open PR (#283).

## 2026-07-18 — pre-recording de-risk pass (Tasks A–D, "等 Eric 期间")

Ran a demo-readiness sweep so recording doesn't fail live. Findings:
- **A — demo-critical paths:** CLI paths all work in `.venv-eval` (live SSO fetch, search, OCR, scoring, tests). **Web UI (Workbench) does NOT run from `.venv-eval`** — it lacks `uvicorn`/FastAPI; the backend runs in the `ai-service` container. Full stack = `docker-compose up` (`docker-compose.yaml`, note `.yaml`). **Action: Eric must `docker-compose up`-smoke the full stack (landing→workbench→cards→highlight→export) before recording.**
- **D — Quick Start clean-clone smoke:** deps present (`requirements.txt`, `.env.example`, `main.py`, `SETUP.md`); `main.py --help` OK; **`--offline --provider deepseek` on SGP 6.4 produced 3 provisions + CSV/JSON** — reproducible path verified end-to-end. Two judge-facing notes: (1) local Ollama is slow on a full pillar (multi-seed × ~20s) → README should say "cloud provider is faster; offline local model is reproducible but slow"; (2) `--offline --indicators 6.1` returning 0 is **correct, not a bug** — verified against `manifest.jsonl`: no SGP seed is hinted to 6.1 (SGP P6 seeds hint 6.2/6.4).
- **B/C — deliverables:** interview Q&A prep + 5-deliverable checklist written to the vault (`interview-qa-prep.md`, `deliverables-checklist.md`). Only open blocker for recording is the Eric docker-compose smoke.

## 📌 PINNED — open questions to raise with the teacher (if we advance)

**1. Search backend for judges: SerpApi vs. free DuckDuckGo.**
Live discovery's generic web search can run on SerpApi (Google-backed, needs a
free-tier API key) or, by default, on **DuckDuckGo HTML search — free, no key,
no signup, no quota**. We ship DuckDuckGo as the zero-config default so judges
who don't have a SerpApi key still get real live discovery out of the box
(verified: DDG returns the correct official sources — sso.agc.gov.sg for the
Singapore PDPA, legislation.gov.au for the Australia Privacy Act, and npc.gov.cn
for Chinese laws). SerpApi is marginally broader. **Question for teacher:** is a
free-tier third-party search API acceptable to the judges, or must discovery use
only key-free/open endpoints? If the latter, DuckDuckGo default already satisfies
it — SerpApi stays opt-in.

**2. China / Great Firewall.** Verified 2026-07: DuckDuckGo and Google are
blocked inside mainland China, but the `china_flk` adapter does **not** need
them — it hits the official national law database `flk.npc.gov.cn` directly
(reachable inside China) plus hardcoded seeds for PIPL and the Cybersecurity Law,
so Chinese-law discovery works behind the firewall. Known limitation: FLK detail
pages are JS-rendered and its JSON API is locked to browser sessions (plain HTTP
gets a 405 / SPA shell), so live *self-verification* of a seed's title needs the
browser driver; without it the seed still surfaces the correct law but tagged
`fallback` (unverified). **Question for teacher:** is browser-rendered fetching
acceptable in the judged environment, or should we pre-cache verified FLK text?

---

## The plan (and where it stands)

| Step | Deliverable | Status |
|---|---|---|
| 1 | Official baseline extracted machine-readable (61 indicators, 809 laws, 1,707 URLs, official scores) | ✅ #72 |
| 2 | Schema/CLI extended to 12 pillars × 7 economies | ✅ #73 |
| 3 | Local full-text corpus of baseline laws | ✅ #74 (+#81 browser path) |
| 4 | Methodology-driven extraction + deterministic scoring for all 61 indicators | ✅ #75 |
| 5 | Self-evaluation harness vs official scores | ✅ #76 (+#80 windowing) |
| 6 | Full 7-economy evaluation run | ✅ complete |
| 7 | Meeting report generator | ✅ #82 |

**Design thesis carried over from Round 1:** the LLM never chooses a number.
It extracts *which published criterion* a provision matches (a categorical,
checkable fact) plus a verbatim quote that must match the source
character-for-character; deterministic Python maps criterion → published
score. Round 2 scales this to 61 indicators by generating both the extraction
spec and the scoring rule from the official methodology JSON — adding an
indicator is a data change, not a code change.

---

## Problems, root causes, fixes

### 1. The Round 2 scope was not what we assumed

**Problem.** Round 1 tooling covered Pillars 6–7 for Singapore/Malaysia/
Australia. The Round 2 database revealed the final round spans **all 12
pillars (61 indicators) across 7 new economies** (CHN, IND, IDN, LAO, MNG,
RUS, THA) — effective overlap with our tool: zero economies.

**Insight that saved the schedule.** The official Round 2 workbook already
contains, per economy, the act name, official reference URLs **and the
official raw score** for every filled indicator. Extracted properly (#72),
it is simultaneously (a) the KNOWN baseline + seed URLs, (b) the indicator
rulebook for the deterministic scorer, and (c) **free ground truth for
self-evaluation** — the same "inventory → corpus → seed-first" play we
validated in Round 1, plus an accuracy metric judges can check.

### 2. Excel mangled the official indicator ids

**Problem.** The methodology sheet stores some indicator ids as numbers:
4.10 arrives as "4.1", and the true 4.1 was typed "4.01" to survive
formatting; same for 12.01/12.1.

**Fix.** Data-driven normalisation verified against the category names
(4.01 = patents = RDTII 4.1; float 4.1 = trade secrets = 4.10; 12.01 =
foreign equity = 12.1), raw id kept as `source_id` (#72). Methodology and
inventory ids align with zero orphans; a guard test fails if they drift (#73).

### 3. `FeatureValue` rejected legitimate float features

**Problem.** The first full India evaluation stalled. Log diagnosis: the 5.3
spec declares `government_equity_percentage` as float; DeepSeek correctly
returned `23.15`; the schema union `bool | int | str` **lacked float**, so a
correct answer failed validation and spun the per-chunk repair loop.

**Fix.** `Union[bool, int, float, str]` (#78). Lesson: the bug had existed
since Round 1 — only full-scale runs on new material exposed it.

### 4. No LLM client timeout: one hung connection = 30 lost minutes

**Problem.** The eval "ran" for 28 minutes at 0.8% CPU with five ESTABLISHED
connections to the DeepSeek API and nothing progressing. The OpenAI SDK
default is 600 s per attempt × retries; a throttled/hung connection occupied
a concurrency slot for ~30 minutes, and `asyncio.wait_for` cannot cancel a
blocked call's socket.

**Fix.** Explicit `timeout` (default 90 s) and `max_retries` (default 1) on
the client, both env-tunable; chunk concurrency also env-tunable (#79).
Hangs became fast failures the pipeline already knows how to absorb.

### 5. DeepSeek v4 is a reasoning model — and that starved extraction

**Problem.** Persistent "Empty response from LLM" errors. Raw API probe
showed `finish_reason: length` with `content: ''` and
`completion_tokens_details.reasoning_tokens > 0`: **deepseek-v4-flash spends
the completion budget reasoning before emitting JSON**; on long legal prompts
it burned the entire budget (and minutes of latency) and returned nothing.

**Fix.** Probed the API for the switch; `{"thinking": {"type": "disabled"}}`
works. Wired into the provider via `extra_body` (re-enable with
`RDTII_DEEPSEEK_THINKING=on`). Health call went from hang/empty to **1.0 s
with correct JSON** (#79). For deterministic JSON extraction, reasoning added
cost and latency without adding accuracy — our accuracy comes from quote
verification + deterministic scoring, not model deliberation.

### 6. Long statutes: the operative clause is buried past any prefix cap

**Problem.** India P7 (our strongest pillar) scored **zero evidence on all 10
rows**. The fetched texts were fine — real 100–170k-char RBI/IFSCA directions.
The eval fed the model the first 60k chars; the retention clauses sit beyond
100k.

**Fix.** Relevance-selected windows: score 4k-char windows by the target
indicator's routing phrases, feed the best segments in document order up to
the budget (#80). **India P7: evidence 0/10 → 9/10, exact score matches 5/10.**

### 7. Scoring semantics: "no evidence" is a score, not a miss

**Problem.** Rows the official evaluators scored 0 were counted as our
misses when we extracted no qualifying evidence — but in RDTII terms, no
qualifying measure *is* score 0.

**Fix.** No-evidence rows score 0 in the comparison; evidence yield is
reported separately so the two effects stay visible (#80).

### 8. JS-only government portals cap corpus coverage

**Problem.** HTTP-path fetch coverage: THA 78%, LAO 72%, IND 49%, CHN 46%,
IDN 31%, **RUS 18%, MNG 15%** — garant.ru, legalinfo.mn, jdih.kominfo.go.id
render via JavaScript.

**Fixes.** (a) An inventory row's multiple reference URLs are tried in order,
so a dead primary link no longer loses the law (#74). (b) `--browser` enables
the Playwright route for JS portals (#81) — refetch in progress. (c) Failures
are recorded as `status=failed` in the manifest; coverage numbers are honest,
never padded.

### 9. Assorted traps that cost real time

- **Registry expected Postgres**: discovery imports hit `localhost:5433`
  unless `DISCOVERY_REGISTRY_BACKEND=file` — the judges' CLI sets it, custom
  scripts must too.
- **Manifest overwrite**: a `--economy`-filtered corpus run wiped other
  economies' manifest records; now merged by key (#81).
- **Buffered pipes**: `python | grep | tee` hides all progress for hours; use
  `python -u`.
- **Playwright/Chromium crash dialogs** (macOS "Python quit unexpectedly"):
  browser-path fetches crash occasionally; harmless (each crash is caught and
  skipped) but alarming — dismiss and let it run. HTTP-first remains the
  default for stability.

---

## Final numbers (full 7-economy overnight run)

**Definitive run (tier calibration + expanded corpus + Wayback recovery):
500 baseline rows end-to-end; evidence for 351 (70.2%); exact official-score
match on 251 — 50.2%. Half of all fully-automated scores match the official
evaluator exactly.** (RUS re-evaluated after archive recovery lifted its
corpus 41%→58%: 58 rows, 53.4% exact.)
Per economy (exact | MAE): LAO **60%** | 0.33, MNG **55%** | 0.37,
THA **53%** | 0.37, RUS **53%** | 0.36, IND **49%** | 0.41, CHN **47%** | 0.44,
IDN **36%** | 0.54.

Calibration effects were real but uneven: MNG +10.7pt, LAO +6.5, THA +5.5,
IND +6.1; CHN flat; RUS −10 (40-row sample noise); IDN −4.5 with a sharp
evidence drop — the conservative instruction over-suppresses on
Indonesian-language texts. Next calibration must be language-aware; the
per-run variance on ≤50-row economies is ±4pt and quoted claims stay
aggregate-level for that reason.

Two findings worth the meeting's attention:

- **Language is not the bottleneck we feared.** Exact-match rates across
  English, Chinese, Thai, Indonesian, Lao, Mongolian (Cyrillic) and Russian
  all land in the 36–60% band; Mongolia — the economy with the *least*
  digitised sources — reached 96% evidence yield once the browser path
  unlocked legalinfo.mn (100% corpus coverage), and Russian scored highest
  of all. The criterion-tier design travels across languages.
- **Residual error is now concentrated in criterion-tier judgement** (which
  numbered option fits), not in missing evidence — the right frontier for
  targeted spec tuning, and visible per pillar in the meeting report.

Composition note for honest reading: exact matches include rows where the
pipeline found no qualifying evidence and the official score is also 0 —
correct abstention, not extraction. LAO's 37/62 exact matches (60%) must
therefore be read alongside its 31/62 evidence yield. Both components are
separable in every eval JSON.

Operational note: a handful of dense Indonesian documents (one maps to 14
indicators) exceeded the 600 s per-document budget and are recorded as
timeouts rather than silently dropped; raising the budget for dense docs is
a cheap follow-up.

## Round 1 pre-submission hardening (Jul 14-15, judge-path audit)

Graded easy->hard testing the way judges probe a tool, plus a clean-room
reproducibility check, caught a cluster of "the judge's exact run breaks"
bugs that no unit test or dev environment surfaced:

| # | Found by | Bug | Why it would eliminate us | Fix |
|---|---|---|---|---|
| 1 | fresh-venv install | **`import psycopg2` outside a try/except** in the batch-prompt builder zeroed EVERY extraction on a clean `pip install` (lean deps have no psycopg2) | Judge follows the README exactly -> headline command writes ZERO output | import moved inside try; DB corrections degrade gracefully (#130) |
| 2 | judge matrix | empty `article` failed the whole submission | mandatory command -> zero files | drop incomplete rows, keep the rest (#121) |
| 3 | judge matrix | `--pdf` rows dropped for empty source_url | the OCR video deliverable -> zero output | source_url falls back to the file path (#125) |
| 4 | native-speaker + matrix | one act shipped under ~22 hallucinated names; 42 near-dup rows for one indicator | citation-fidelity point deductions | authoritative library names (#123), dedup (#122), per-(law,indicator) cap (#127) |

Two runnable gates now guard against regressions: `tools/check_reproducibility.sh`
(fresh venv + headline command) and `tools/judge_test_matrix.py` (5 tiers,
18 cases, incl. the live network path and honesty stress). Both green.

**The lesson for the pitch:** Round 1 is not lost on capability (golden set
100% F1, judge matrix 18/18) — it is lost when the judge's exact run breaks.
The only way to find those breaks is to reproduce the judge's exact run: a
clean virtualenv, the documented command, graded output. Every bug above was
invisible to unit tests and the dev environment.

## Pre-submission polish (rubric-driven, Jul 14)

Each item traces to the judges' published scoring language:

| Rubric line | Before | After | PR |
|---|---|---|---|
| "exact article and paragraph required" | 2/8 rows carried an article on the official scanned sample | **7/8** — deterministic backfill from the nearest legal heading (EN/ZH/TH/ID/RU forms), inferred rows flagged in notes; empty beats wrong | #89 |
| OCR audit trail | scanned docs silently reported `pdf_is_scanned=False`, no CER | `pdf_is_scanned=True`, measured `ocr_quality_cer=0.064` on the official sample | #88 |
| "error below 5%" (OCR) | — | Honest known-limit: tesseract plateaus at 93.6% mean confidence on the official scan; DPI/PSM sweeps verified unhelpful (200 dpi wins per-page but loses full-document). We measure and expose per-page confidence instead of claiming a number we cannot back | log |
| "zero points if only pre-downloaded PDFs" | untested without search keys | Live-crawl smoke: **28 provisions live-discovered from the SGP portal with no SerpAPI key**, fixture fallbacks excluded from formal output | smoke |
| "mis-spelt country, edge cases" | missing-PDF path dumped a raw traceback | clean `Error: PDF not found` (exit 2); economy/pillar errors verified clean | #90 |
| "your actual operational cost" | telemetry collected, never surfaced | every run prints and records measured cost (SGP P6 offline: 13 calls, **$0.0139**) | #91 |
| Docker deployment | untested | full 5-service stack builds and runs healthy (`/health` ok, frontend 200); caveat: the compose file mounts a local Vertex key path that will be an empty dir on clean machines — noisy but non-fatal under the default DeepSeek provider | tested |

## The review console itself was iterated live (Jul 14, one afternoon)

The legal-review session was not just a QA pass — it stress-tested the review
tooling itself, and every gap found was fixed **while the reviewer worked**:

| # | Found by | Gap | Fix (same session) |
|---|---|---|---|
| 1 | reviewer screenshot | Cards showed indicator codes (P6-I1) but not what the indicator *means* — the question being judged was missing | Official category + scoring criteria injected into every card ("THE QUESTION" block) |
| 2 | reviewer | Mapping rationales truncated mid-sentence (the 300-char submission-spec clip leaked into the review view) | Full 2–3-sentence rationales regenerated for all 35 evidence cards, labelled `[regenerated for review]` |
| 3 | native-speaker check | Chinese cards quoted policy-principle clauses (ride-hailing pricing!) as cross-border-data evidence — structural curation (has article + long quote) ignored semantic relevance | Relevance-aware curation (quote × indicator phrase table); textbook-correct localization/retention clauses surfaced (网约车办法 §27 was there all along) |
| 4 | reviewer (no Thai) | Thai/Chinese/Russian quotes unreviewable by an English-speaking lawyer | Machine translation blocks auto-added to all 16 non-English quotes, clearly labelled |
| 5 | reviewer | Adjudication cards had scores but no evidence and no links — unjudgeable | Official URLs backfilled 10/10; engine quotes re-extracted 5/10 (+ translations); "judge from the source" guidance for the rest |

Five find-fix cycles inside one working session, reviewer never blocked more
than minutes. This is the human-in-the-loop claim made concrete: the loop
improves not only the data but the tooling around it.

## Legal review results (Jul 14 session, exported verdicts)

44 verdicts + 33 written notes from the legal lead:

- **Evidence precision (human-verified, final): 70% combined (31/44
  decided)** — Round-2 pack 19/27, Singapore pack 12/17 after the Payment
  Services Act cards landed 8/8 correct (semantic curation validated).
- **Adjudication (Task B): the official evaluators were right in 7/7
  disagreements reviewed** — every engine over-score quoted a principles/
  objectives provision. The rule is now encoded in the extraction
  calibration ("statements of principle are not measures").
- **Inferred citations (Task E): 2/2 sampled flagged for granularity**
  (heading right, sub-paragraph missing, e.g. "2" vs "2.i") — inference is
  clause-level, reviewers want sub-clause; logged as a known limit.
- **NEW laws: 4 of 5 signed off** (SGP PDP Regulations, MYS Credit Reporting,
  NSW PPIPA, QLD IP Act). Archives Act 1983 flagged "needs work" — the
  statute does not specify digitised archives; kept as a lead, excluded from
  signed-off claims.
- **The "hallucination" that wasn't:** reviewer flagged a quote as invented
  (not in the named act). Investigation: the quote was char-verified at the
  exact URL shown — but `source_legislation` named the statute the provision
  *discusses* (PSSA 2007) instead of the document it is *quoted from* (RBI
  Payment Aggregator Guidelines). Same-day fix: rows now carry
  "quoted from document: <title>" whenever the two diverge (#107). The
  verbatim-verification chain held; the label was the misdirection.
- Residual note themes: rationale sentences occasionally cut mid-sentence by
  the token budget; circulars/policies flagged as weaker evidence than
  statutes (a future law-type weighting); one article-granularity miss
  ("Section 2.1 not paragraph 4").
- Tasks B (score adjudication) and E (citation spot-check) deferred — B goes
  to the visiting trade-law professor on Thursday by design.

## What the meeting can claim

1. **The full official methodology is executable**: 61/61 indicators have a
   generated extraction spec and a deterministic, auditable scoring rule
   citing the published criteria (verified: a 49% e-commerce equity cap
   scores 1.0 on 12.1 with a verbatim quote, and is correctly *rejected* for
   3.1 because the official exception assigns e-commerce equity to P12).
2. **Accuracy is measured, not asserted** — against the official Round 2
   database itself, with coverage, evidence yield, exact-match rate and MAE
   per economy and per pillar (`docs/round2-meeting-report.md`).
3. **Every failure mode found became a shipped fix** (#72–#82), and the
   fixes are regression-tested (500+ automated tests).

### Tier 6 edge cases + the "offline matrix is not hermetic" insight (#137)
**Problem.** The judge matrix had no coverage for malformed *arguments* (as
opposed to malformed documents) — duplicate pillars, a text file renamed `.pdf`,
`--pillar 0`. These were validated by hand but nothing locked them in.
Separately, a matrix run flagged the mixed-case-economy case as FAIL (exit 2, 0
rows, 15.2s).
**Fix / finding.** Added Tier 6 (3 deterministic offline cases, all green).
Investigating the "failure": `economy_code()` already lowercases input, and
re-running `--economy sInGaPoRe --pillar 6 --offline` writes 3 provisions
cleanly. The FAIL was a single DeepSeek API blip during extraction — because
**offline matrix cases still call the live LLM** (retrieval is local; mapping is
live). Documented in the harness/PR that the matrix is a pre-submission *gate*,
not a hermetic unit test, so a lone API timeout can flake one case; re-run to
confirm. No code defect.

### NEW-discovery false-positive: an economy's own flagship law flagged NEW (#138)
**Problem.** Sweeping for NEW laws (`tools/discover_new_laws.py`) on Malaysia
reported **Malaysia's own PDPA 2010 as a NEW discovery**, plus hallucinated
siblings where a Malaysia PDPA page was relabelled "Singapore PDPA 2012" /
"Hong Kong PDPO 1996". Root cause: live discovery emits verbose titles
(`Malaysia Personal Data Protection Act (PDPA), 2010, No. 709`) and
`normalize_law_name` stripped parenthesised numbers + years but not a leading
country word or a bare `No. 709`, so the title never reconciled to the KNOWN
baseline. Submitting a country's flagship statute as a "new find" is exactly the
kind of error that torches the 40% accuracy score.
**Fix.** `normalize_law_name` now also strips a leading economy/nationality
prefix (keys are already `(economy, name)`-scoped) and bare `No./Act/Cap./
Chapter N` tokens. Malaysia PDPA + its mislabelled variants reconcile to KNOWN;
genuine finds (Spam Control Act 2007, Identity Verification Services Act 2023)
stay NEW. +3 regression tests, 519 pass.
**Method note.** Discovery candidates (law name/url/quote/indicator) are
code-version-independent; only NEW/KNOWN *classification* changed, so in-flight
sweeps can be re-reconciled with the fixed `is_known_law` instead of re-run.

### NEW-discovery triage: turn a noise dump into ranked leads (#140, #141)
**Problem.** After the false-NEW normalization fixes, the sweep still dumped
~100 undifferentiated rows on a legal reviewer: international agreements (CPTPP,
SAFTA), off-topic legislation a broad crawl dragged in (customs charges,
pasture-seed levies mapped to P7), foreign-relabelled hallucinations (a Malaysia
PDPA page tagged "Hong Kong PDPO"), and — subtlest — a quote from one statute
labelled with a *different, already-known* statute's name (SGP "PDPA 2012" whose
source URL was `/Act/FSA1993`, the Financial Services Act).
**Fix.** `build_discovery_report` now attaches a reviewer verdict — CANDIDATE /
REVIEW / REJECT with a reason — to every NEW candidate and sorts strong leads
first (#140). `classify_new_candidate` rejects international instruments,
foreign-name-on-home-domain mislabels, and off-topic finds (via an optional
pillar-topical regex), and REVIEW-flags off-official-domain provenance. A
follow-up (#141) demotes any NEW_PROVISION of an already-KNOWN law — the shape
the FSA-mislabelled-as-PDPA garbage takes — from CANDIDATE to REVIEW. Verdicts
rank and explain; they never drop a row.
**Finding (honest).** With the mandatory economies triaged: MYS and SGP surface
**no genuine new P6/P7 domestic law** beyond the KNOWN baseline (the ESCAP
inventory + library are comprehensive for these); the real leads are in AUS
(Identity Verification Services Act 2023, Privacy Amendment (Public Health
Contact Information) Act 2020). Not padding the NEW list with mislabels is
itself the accuracy win.

### Round 2 discovery: baseline built, live sweep gated on a search backend (#143)
**Done.** Wired the official Round 2 Database (`round2_inventory.jsonl`) into
`known_law_index` as the KNOWN baseline for the seven Round 2 economies, with
multi-act cell splitting and bilingual (English + native-script) identity keys,
plus CHN/THA official domains for candidate triage. NEW/KNOWN reconciliation for
these economies is now correct.
**Blocker found.** The actual CHN/THA NEW-law *sweep* returns 0 live candidates
in this environment: `discover_and_extract` only accepts `retrieval_mode ==
"live"` candidates, but (1) the generic `search_engine` adapter needs
`SERPAPI_API_KEY` (unset) and otherwise returns fixture fallback; (2) the
`china_flk` adapter falls back because the FLK national-law database is a
JS-rendered SPA the crawler cannot render; (3) the `thailand_ocs` adapter hangs
(2-min timeout). So without a search backend the sweep can only re-surface the 3
registered seed URLs — all already-KNOWN flagship laws.
**Resolution path.** A `SERPAPI_API_KEY` unblocks it: the search_engine adapter
then does site-scoped Google search over `*.gov.cn` / `*.go.th`, bypassing both
the JS FLK portal and the hanging OCS adapter. Re-run
`tools/discover_new_laws.py --economy China/Thailand --pillar all` once set.

### R1 structured-output audit + fragment-quote filter (#150)
**Problem.** Generating the R1 mandatory-scope output (SGP/MYS/AUS × P6/P7) and
auditing it rigorously revealed quality issues invisible to the test suite: the
default/live path pulls in trade agreements, off-topic statutes (Fire Safety,
Petroleum) and a blog title ("Mastering the must-dos of data protection"); the
offline path has mid-sentence fragment quotes ("data processor", "personal
data", "Exemption—compromise to cybersecurity") and is dominated for AUS by ~35
Queensland state-law provisions.
**Caught my own error.** Initially flagged the P7-I1 title-quotes (quote == law
name, e.g. "Privacy Act 1988") as garbage — but the golden set carries exactly
these as the legitimate "framework exists" evidence pattern (score 0.0 for
"lack of framework"). The fix had to preserve them.
**Fix (#150).** validate_submission_rows drops a row whose verbatim quote is a
fragment: `< 45` chars AND not the law title (token-subset match, so a country
prefix / "(PDPA)" acronym is tolerated). Verified 0/29 golden cases dropped.
**Reverted a bad idea.** Enriching the thin MYS curated library with PDPA
Section 9/10 excerpts backfired — the pipeline mapped them to fragment quotes and
a wrong indicator (Retention Principle → P7-I5). Reverted; kept the clean 2-row
MYS. Lesson: adding library text does not guarantee a good mapping.
**Still open.** AUS QLD-state over-representation and thin MYS coverage remain —
a library-curation decision, not a code fix.

### The reuse cache we shipped broke our own test suite — on the second run (#177 → #179)

The document-level extraction cache (#177: fingerprint the source text, serve a
repeat extraction from cache, skip the LLM — 29.6s → 0.02s measured) passed its
own tests and the full suite... once. On the *second* consecutive full-suite run,
an unrelated streaming test failed: the cache had written the test's content to
the live DB during run one, so run two replayed from cache — which emits no
`rejected` events — and the assertion died. CI on a fresh DB would never have
caught it. Fix (#179): an autouse conftest fixture no-ops the cache helpers for
every test (the dedicated cache tests re-enable them locally), verified by
running the full suite twice back-to-back. **Lesson: any feature that writes to
a live store must be quarantined from the test suite, and "hermetic" is only
proven by the second run.**

### The rigor gate caught *us* — twice (#184, #185)

The NEW-law sweeps produced 20+ plausible finds. Before banking, each ran
through the double gate: hand re-verification against the official portal +
the automated `is_known_law` novelty check. The gate rejected ~12 of our own
candidates — including Singapore's Electronic Transactions Act, Malaysia's PDP
Standard 2015, Australia's DAT/AML-CTF/SOCI Acts, and China's PIPL/DSL/CSL
(all already in the official baseline), plus the spent COVIDSafe cross-border
ban (repealed — "in force" would have been an over-claim). The library
snapshot tests then caught the first promotion batch red-handed: two entries
(CCA 2010, CMA 1998) were already KNOWN, and the count assertions refused to
pass until they were retracted. **Lesson: after the July over-claim
embarrassment, the anti-embarrassment machinery is now infrastructure — the
gate rejecting our own work is it functioning, not failing.**

### "Needs a human browser" was wrong — our own fallback got through (#190)

Three research passes concluded NSW's legislation portal (Cloudflare JS
challenge) required manual browser work: curl 403, WebFetch 403, AustLII 403.
Wrong conclusion — the sweeps had only tried *plain HTTP*. The project's own
Playwright fallback (the same cascade behind the Mongolia 15%→100% story)
walked through the challenge, fetched 164K chars, and PPIP s 19(2) was captured
verbatim and banked (P6.4). Per Dong's directive, the fetch layer now reports
loudly when *every* strategy fails — which strategies were tried and that a
manual browser is needed — instead of silently skipping. **Lesson: exhaust your
own tool cascade before declaring defeat; and when the tools truly fail, tell
the user — a silent skip is a lie of omission.**

### The research agent corrected our own brief (Act A1354 → A1727)

The Malaysia deep-dive was briefed to fetch "PDPA Amendment Act 2024 (Act
A1354)" — a number we supplied from memory. The agent checked the official
gazette, found no such act, and came back with the correct **Act A1727** plus
the commencement gazette (P.U.(B) 522) pinning each section's in-force date.
The wrong number never reached a document. **Lesson: identifiers (act numbers,
section numbers, dates) get verified against primary sources like everything
else — including the ones we wrote ourselves.**

### The judge's command was a lottery — and one draw flooded Singapore with Chinese law (#196, #199, #201)

We ran the judge's exact default command three times. Draw one: 40 minutes,
7 clean rows. Draw two: live search surfaced a multi-jurisdiction legal digest
plus two giant statutes (a 252K-char Act among them) — Pillar 6 alone burned
1,825 LLM calls ($2.06), the run took 67 minutes, and the output claimed
"18 NEW laws" for Singapore that included China's PIPL, India's DPDP *Bill*,
an ASEAN framework, and a consultation paper. Nothing in the old gates could
catch China or India by name — they are covered Round-2 economies that cannot
be blanket-blacklisted. Three fixes, all deterministic and loud, all
golden-verified (29/29, 0 false positives): (1) candidates the noise-gate
would reject anyway are skipped BEFORE the expensive fetch+extract; (2)
live-discovered documents are capped at RDTII_MAX_LIVE_DOC_CHARS with an
honest "partial doc" note per affected row; (3) an economy-aware
foreign-jurisdiction gate (China PIPL dies in a Singapore run, survives in a
China run) plus a non-statute gate (bill/draft/consultation/digest).
**Lesson: run the judge's command more than once — variance is where the
embarrassment hides.**

### Our own banked NEW law silently missed the formal run (#198)

The banked Banking Act 1970 s.47 entry produced no output row on the judge's
command. Root causes: the banked text was a single sentence (217 chars) — too
thin for the extractor to map reliably — and the citation depended on the
model volunteering an article. Fixed by enriching the entry to the full
s.47(1)–(5) verbatim from SSO (re-verified at the official URL) and adding a
promoter-verified `article_hint` manifest field that build_row uses as a
deterministic fallback, so a banked law can never drop on "missing: article".
The promote tool now warns on thin texts and takes --article. Offline P7:
5 → 7 provisions, Banking Act back with "Section 47". **Lesson: bank the full
section, not a sentence — and never let a citation depend on model output.**

## 2026-07-16 overnight — beyond-6/7 discovery, and two portals that changed under us

### The P6/P7 NEW space is largely exhausted — and that is the honest finding

We hunted the empty localization indicators (6.1/6.2/6.3) for Singapore and
Malaysia with two deep research passes. After the double gate (verbatim
re-verify + `is_known_law`), **zero were bankable as NEW** — and that is the
rigorous result, not a miss. Singapore's one genuine hard-storage rule is
Companies Act 1967 s.199(4) ("...sent to and **kept at a place in Singapore**"),
but the Act is KNOWN, so it is KNOWN evidence, not a discovery. Everything else
(MAS Outsourcing, BCM, CCoP, tax record-keeping) is conditional-access, not
localization; Malaysia's BNM RMiT/Outsourcing are conditional-flow (6.4) and the
only openable verbatim is the superseded 2020/2019 text (the current RMiT is
behind an AWS WAF that beat curl, WebFetch, and Playwright). We declined to pad
the NEW list with a control catalog or superseded policy text. **Lesson: an
honest "no new law here" beats a padded one — the discovery count is a claim we
have to defend row by row.**

### The one P6/P7 NEW left standing — and a fetch bug it exposed (#213)

Australia's **Cyber Security Act 2024 (No. 98, 2024)** — the country's first
dedicated, standalone cyber Act (device security standards, ransomware payment
reporting s.27, Cyber Incident Review Board) — is genuinely NEW (distinct from
the KNOWN SOCI 2018) and fills the empty **7.2** slot. Banking it surfaced a
real bug: our source-verification fetcher forced `legislation.gov.au` to the
browser strategy, which only ever gets a JS shell — so it could *never* verify
an Australian quote. The statute body lives only at the `.../text/original/pdf`
endpoint. Fix: any URL whose path ends in `/pdf` (not just `.pdf`) now forces
the pdf strategy first, on any domain. Clean PROMOTE, verbatim re-confirmed by
hand against the Authorised Version PDF. **Lesson: a "usable enough" JS shell is
the most dangerous fetch result — long enough to look fine, empty of the law.**

### Beyond-6/7 capability, made tangible (#214)

To show the tool scales past the mandatory pillars with something judges can
click, we banked one rock-solid NEW subsidiary instrument: Malaysia's **Consumer
Protection (Electronic Trade Transaction) Regulations 2024** [P.U. (A) 449/2024]
→ **12.9** (online consumer-protection framework), verbatim-verified at the
official AGC gazette PDF. Two other candidates were deliberately NOT banked:
AUS BOSE Determination 2022 (`is_known` → KNOWN, Online Safety Act family) and
MYS Income Tax Act s.82C e-invoicing (a real 2023/24 provision, but no clean
RDTII P12 indicator — 12.4.x are payment limits, not tax admin). SGP Online
Criminal Harms Act 2023 was also dropped: `is_known` → KNOWN. **Lesson: quality
over quantity — three verified rows beat ten that a legal reviewer would strike.**

### Singapore SSO went behind an AWS WAF — a silent break we caught (#215)

Mid-session, verbatim verification started failing for *every* Singapore entry.
Root cause: `sso.agc.gov.sg` now sits behind an AWS WAF — the HTML endpoint
returns **HTTP 202 with an empty body** to curl / WebFetch (0 bytes,
`x-amzn-waf-action: challenge`). This is a portal that worked yesterday and
stopped today; left unnoticed it would have quietly disabled our
anti-hallucination gate for Singapore right before submission. The `?ViewType=Pdf`
endpoint is *not* challenged, and the browser cascade already falls back to it —
so reordering the SSO hint to `["browser", "http_ua"]` restores verification
(full PDPA 191KB; Banking Act s.47 re-verified). **Lesson: portals change under
you. When a crawl that used to work stops, that is a finding to surface loudly,
not a transient to retry — and the fix belongs in the SITE_HINTS registry with a
date.**

### A discipline slip, recorded honestly (#216)

While shipping the SSO fix I merged the PR before noticing it broke a hard-coded
strategy-order assertion. Caught it immediately after, updated the test to the
new expected order (and added an assertion for the `/pdf` routing fix), re-ran
the full suite green. **Lesson: the test suite is the gate, not a formality —
read the pytest tail before `gh pr merge`, every time.**

## 2026-07-17 — a validation catch: "7.2" was really 11.1 (the anti-over-claim gate earning its keep)

Overnight I banked the AUS **Cyber Security Act 2024** as NEW evidence for RDTII
**7.2** (dedicated cybersecurity framework), and updated the README / brief /
heatmap to claim the empty 7.2 slot was filled. Before finalising, I ran a live
end-to-end extraction over the four laws banked that night. Three mapped as
expected (MYS CP(ETT) → 12.9; TAS PIPP 9 → 6.4; WA IPP 9 → 6.4/7.1). The Cyber
Security Act did **not**: the pipeline mapped its provision content (device
security standards s.14, ransomware payment reporting s.27) to **11.1
(Standards)**. Root cause: 7.2 is a *framework-existence* judgment, not a
content indicator the extractor reproduces from a single provision — and
`run_library` passes no indicator hint to `run_extraction`, so content decides.

Corrected honestly rather than shipping the claim: the law is re-hinted **11.1
(pipeline) + 7.2 (analyst, flagged for legal review)**, counted as a beyond-6/7
(Pillar 11) find, and the docs now say so — no clean 7.2 row is asserted that the
tool does not produce. **Lesson: a manifest indicator hint is a retrieval label,
not a mapping guarantee — validate a banked law's indicator with a real
extraction before writing it into the pitch. Verify before presenting.**

## 2026-07-17 — extraction-reproducibility audit of all 21 banked NEW laws

After the Cyber Security Act 7.2→11.1 catch, I re-ran every banked NEW law
through `run_extraction` (3× for flagged cases) to see whether the pipeline
reproduces the hinted indicator. 16 of 21 auto-reproduce; 5 do not — the banked
excerpt of a subtle provision (biometric restrictions, offshore outsourcing,
computer-access assistance orders, credit-information security, record
retention) yields an empty or divergent mapping. Enriching one (Digital ID s48)
to fuller context changed it from empty to 7.4 — still not the hinted 7.1 —
confirming the divergence is about *which subtle indicator*, not just excerpt
size. Rather than fabricate alignment, I flagged all five with a manifest
reproducibility note: their indicator is a legal reading pending legal review,
which is the designed human-in-the-loop step. Crucially, every RDTII cell they
touch is independently covered by an auto-reproducing law, so no coverage claim
depends on a flagged one. **Lesson: separate the two claims — "we discovered and
verbatim-verified a NEW law" (rock-solid) from "the pipeline auto-maps it to
indicator X" (only for 16/21). Report each honestly; the indicator for subtle
provisions is a human-review call, not an automated fact.**

## 2026-07-17 (pm) — official scoring, live-run pollution, and fetch resilience

### The official answer key reframed everything
Located the official RDTII Round-1 database (`…/ESCAP-RDTII-2.1_ Round 1
Database.xlsx`): **one raw score (0/0.5/1) per indicator per economy**, with the
law it cites — AUS/MYS/SGP P6/7 is only **~11 rows each**, not the 47/70/17 our
runs emit. So the judge scores per-INDICATOR; our many provisions collapse into
9 indicator scores. Built `tools/score_vs_official.py` to fold any run into that
shape and diff it, flagging three things: **NEW-evidence divergence** (a NEW law
we found changes the score vs the official basis — a Stage-2 discovery win if
real, e.g. AUS 7.2=0.5 on the 2018 SOCI Act vs our Cyber Security Act 2024; an
over-claim to drop if hallucinated), **hallucination**, and **gaps**.

### Live discovery is 40–75% hallucination — offline library is clean
The comparator immediately exposed that the live judge command produces garbage:
one URL claimed by 3–5 different law names (the model inventing names on a real
register page), plus out-of-scope goods laws ("Wine Export Charge Act" → 7.5).
AUS 20/47, SGP 33/70 rows hallucination-flagged; the **offline library run is
0**. Lesson: **the raw live output is a lead list to verify, not a submission —
the clean core is the verified library.** Two new validator gates: drop a
goods/agriculture law mapped to P6/P7, and flag (never drop) 3+ distinct law
names on one URL.

### A hallucination metric that cried wolf
First cut counted ROWS per URL — but one law legitimately maps to several
indicators (several rows, one URL), so a clean offline run showed 16/17
"hallucinated". Fixed to count **distinct BASE-act names** (dropping "— s.12A"
section suffixes, normalised to alphanumerics): the three A1727 provisions on one
URL are one act, not three. Offline MYS 16→0; live runs still show the real
pollution. Lesson: **a false-positive safety signal is worse than none — it
trains you to ignore it.**

### Resilience: never silently miss a KNOWN law during judging
SGP 7.2 (official 0, basis Cybersecurity Act 2018) was an uncovered gap; banked
s.7 as KNOWN, verbatim from the official SSO PDF — which required routing
`?ViewType=Pdf` *query* URLs to the pdf strategy (they'd fallen through to
Playwright, which can't render a download), and noting SSO's AWS WAF fingerprints
httpx but passes curl. Then wired the pre-downloaded KNOWN corpus
(`data/known_corpus/`, ~175 laws) as a **last-resort run-time fallback**: official
site → Wayback → Google Cache → local cache. Re-fetching the gaps recovered the
**MYS Income Tax Act** (official hasil.gov.my URL now 404s) from a **Wayback
snapshot** — 1.37 M chars, the official basis for MYS 6.2 + 7.3 — exactly the
"work like a human, fetch from the archive" the brief anticipates. Also fixed a
data-loss footgun: the corpus builder rewrote the whole manifest on a
per-economy run; it now merges. Lesson: **the archive fallback isn't a nicety —
official URLs rot, and a judge's run must degrade gracefully to it.**

## 2026-07-17 (pm) — law-currency audit: are we citing the latest, in-force version?

Checked our currency handling against the methodology (internal guide p.8:
"excludes pending draft and repealed measures"; output template col.4
`last_amended` = "year of most recent amendment"). Three defects found and fixed.

**A "current as at" date was masquerading as an amendment year (#255).** The QLD
Information Privacy Act 2009 seed stored `last_amended: 2026-07-01` — that is the
consolidation's *currency* date, not an amendment. Every QLD row reported
`last_amended=2026` for a **2009** Act. Root of the low fill-rate was deeper: two
capable helpers were **built, unit-tested, and never wired in** —
`timeframe_extractor` (status + amendment-date parsing) and `assess_currency`
(version-fingerprint drift). Output's `last_amended` was a dumb year-grab over
two metadata fields, blind to the document body. Fix: cleared the QLD field
(verified against the QLD portal — amendment history is in external endnotes we
don't cache, so we do **not** guess a year), and wired `timeframe_extractor` into
`build_row` as a body-text fallback using amendment-specific patterns, so an
enactment year or a currency date is never promoted. Empty beats a wrong year.

**Currency was invisible in the output (#256).** SSO / legislation.gov.au / FLK
canonical URLs already serve the current consolidated version by default (AUS is
explicit: `/latest/text`), so we weren't shipping stale law — but a reviewer
couldn't *see* that. Threaded the curated `version` label + `currency_checked_at`
into the seed row note: "current version: 2020 Revised Edition (currency verified
2026-07-13)".

**Repealed laws weren't excluded (#257).** Drafts/bills were already dropped;
repealed weren't. Added a high-precision validator drop on the explicit
`(Repealed)` title marker that official portals stamp — while deliberately
keeping in-force "Statute Law (Repeals) Act" and quotes that merely mention
repeal (precision over recall: dropping a valid law costs more).

Lesson: **a graveyard of capable-but-unwired helpers is its own failure mode** —
the currency logic existed for weeks and did nothing because nothing called it.
Audit that the code you *rely on* is actually on the call path, not just present.

## 2026-07-17 (night) — scoring integrity: right number, wrong reason, fabricated tier

Three defects, all surfaced by the legal lead reading actual extractions — the
kind a numeric benchmark hides because the *score* looks fine.

**Right score, wrong law (#259).** A 7.5 row ("government access to personal data
without judicial oversight") scored 1 citing **PDPA 2012 s59(5)** — but that is
the data-protection Commission's own *"Preservation of secrecy"* clause, which
permits it to disclose information "(a) where the consent of the person ... has
been obtained". A consent-gated safeguard, and the wrong actor (the DPA, not law
enforcement). The correct basis is the Criminal Procedure Code 2010 s39/40.
Fixed with a deterministic veto at the single feature-assembly point: if a 7.5
access/disclosure is conditioned on the subject's consent, the government-access
feature is cleared (→ 0). Precise — real police-access quotes and "without
consent" phrasing are untouched.

**A fabricated score tier (#260).** A 7.4 row scored **0.25**. The official 7.4
scale is strictly 1 / 0.5 / 0 (DPO all sectors / DPO one sector / no DPO) — there
is no DPIA-only tier; `score_7_4` invented the 0.25. Verified against the
methodology sheet: the whole official Round-1 key uses only {0, 0.25, 0.5, 1};
**0.25 belongs to exactly one indicator, 3.4** (Pillar 3), and **0.75 appears
nowhere**. Fix: DPIA-only → 0; and, per the lead's new standing rule ("every
score hard-coded to official, zero scoring hallucination"), added
`OFFICIAL_ALLOWED_SCORES` + a runtime guard that snaps any off-spec score to the
nearest official value and logs it, plus a test that exhausts every P6/P7
scorer's feature space against the official set. (Also flagged: official P6 has
6.1-6.4 only, yet a `score_6_5` exists — returns 0/1 so no fabricated tier, but
possibly out of scope; left for review.)

**A coverage hole behind it (#261).** SGP 7.5 came back empty even though the
CPC s39 seed (hint 7.5) was loaded — the broad keyword classifier re-derived the
indicator and mis-routed the "access computer" clause to 7.1. `indicator_hints`
only ever *selected* seeds, never steered the mapping. Fix: when a curated hint
in scope produces no mapping, run a targeted extraction for exactly that
indicator (`target_indicators` bypasses the classifier). Verified live.

Lesson: **a matching score is not a correct score.** The benchmark's
exact-match rate can't see a consent clause read as surveillance, a fabricated
0.25, or the right law filed under the wrong indicator — only a human reading the
evidence catches those. Deterministic scoring must be pinned to the official
scale, value by value.

## 2026-07-18 — a forensic review of four Australian laws (external research, verified)

The legal lead ran four Australian provisions through an external deep-research
model, then had us verify each claim against the official guide before acting.
Two produced real fixes; both were then re-confirmed by a second, sourced
research pass quoting the guide verbatim.

**7.5 under a judicial warrant is not "without oversight" (#265).** Crimes Act
1914 s3LA ("a constable may apply to a **magistrate** for an order ... to access
data") was read as unfettered government access. The official 7.5 criterion:
*"Score of 1 ... if the government is allowed to access personal data **without a
court order** ... Requiring a court order ... gets a score of 0."* Extended the
#259 veto (which only handled consent) to judicial authorisation — warrant /
court / judge / magistrate order → feature cleared → 0. Negations ("without a
warrant") and genuine warrantless police access (SGP CPC s39, official 7.5 = 1)
are untouched.

**Government-data measures are not scored (#266).** Archives Act 1983 s24 (bars
destroying a "Commonwealth record") was scored at 7.3. The guide: *"any
regulatory measure that is applied to **government data does not get scored** ...
the indicators are ... designed to focus on ... **commercial transactions**."* A
latent `_excluded_if_gov_only` feature existed but relied on an LLM flag the
model never set for the Archives Act. Added a deterministic validator drop
(government-record object, guarded by a personal/commercial-data check), verified
on live output: drops Archives Act s24 + the Evidence Act "official records of
State" clause, keeps the Identity Verification Act's facial-image duties and PDPA.

**Verified-but-not-adopted.** Indicator WEIGHTS are official (12 pillars
equal-weighted and averaged; within-pillar weights, e.g. P7 = 31/31/16/16/6) but
we compute no aggregate index score (we emit evidence rows + per-indicator
scores; judges aggregate), so weights stay documentation only. Indicator **6.5**
is absent from the Round-1 database and methodology sheet (P6 = 6.1-6.4), but the
guide's Pillar-6 indicator figure was not accessible to confirm the full
framework — so the phantom `score_6_5` is flagged, not ripped out, pending a
scope decision. Full verified/not-adopted table lives in the vault.

Lesson: **external research is a lead, not a source.** Every claim was quoted
back to the official guide before it touched code; the two that survived were
real, the weights/6.5/DTRS specifics that couldn't be sourced were logged as
"reference only."

## 2026-07-18 — precision-first mapping eligibility gate

Legal review showed the remaining failure class was not fabricated text: the
quote and keywords were real, but the indicator was wrong and the Analyst then
wrote a plausible post-hoc explanation. The fix moves acceptance before scoring
and rationale generation. Keyword routing now records local spans and refuses to
join words across sentences; curated laws route only to reviewed indicator
hints; and a deterministic boundary check plus an independent all-P6/P7
verifier must select the candidate indicator with exact evidence spans or NONE.

The CSV confidence column now means mapping confidence rather than discovery
source confidence (the source value remains in JSON). Formal output excludes
ambiguous, contradicted, flagged and sub-0.8 mappings unless the researcher uses
`--include-review`. Rejections expose the candidate, verifier-supported labels,
exact spans and exclusion reasons. Legal-review exports can be converted into
pending golden hard negatives/positive reassignments, and evaluation now reports
accepted precision, abstention, acceptance rate and indicator confusion.

Regression result: 640 Python tests pass and the production frontend builds.
The offline legal golden set accepts all 16 positive mappings, rejects all 13
explicit negatives, and reports 1.0 accepted precision/recall with no indicator
confusion. A fixed-model full-mode run remains an environment follow-up: all
provider key entries in the local `.env` are empty, so no external model result
was claimed or substituted with the offline score.

## 2026-07-21 — MYS 7.5 was the one official cell no seed covered

The Round-1 submission-eve `--offline` run (three economies, pillars 6-7)
covered 15 of the 16 official non-zero economy×indicator cells. The missing
one was Malaysia 7.5 (government access): every MYS library seed hinted at
6.2/6.4/7.1/7.3/7.4, so the deterministic backbone had nothing to serve and
the cell silently produced zero rows. Live discovery had previously found the
Cyber Security Act — which is why the older live outputs covered the cell and
the offline run did not.

Fix: bank the exact law the official answer key cites — Cyber Security Act
2024 (Act 854) s46, MYS 7.5 = 1, Horizontal — as a KNOWN seed
(`mys-cyber-security-act-2024-act-854-s46`). s46(1)-(2) were verified verbatim
against the official AGC Laws of Malaysia PDF (lom.agc.gov.my; the answer
key's own reference URL is a law-firm mirror, so the seed records the official
portal instead). `promote_new_law.py --verify` correctly refused to bank it as
NEW (`REJECT_KNOWN` — the Act is in the official Legal Inventory), confirming
the novelty triage works; the seed was added manually with origin=known.

Library: 35 → 36 entries; count test and a targeted
`lookup("MYS", indicators=["7.5"])` regression test updated in the same
commit. Offline MYS 7.5 coverage is now genuinely 16/16 by construction.

## 2026-07-21 — 7.1/7.2 fall-through scored "absence" from one document

Error taxonomy over the 500-row benchmark (251 exact / 173 mismatch-with-
evidence / 78 no-evidence) showed the single largest mismatch family was
over-scoring official-0 cells, and 7.1/7.2 led it. Root cause: both bespoke
scorers fell through to 1.0 ("no framework") whenever the LLM answered false
to the existence features. But score 1 on these inverted indicators is an
economy-wide ABSENCE claim — something no single provision can establish; a
document can only ever prove a framework exists (0 or 0.5). The benchmark
confirmed the asymmetry empirically: there is not one official 7.1/7.2 = 1
row in the 500, so the fall-through 1.0 had zero true positives and 12 false
ones (11 straight 0->1, one 0.5->1).

Fix: fall-through now returns 0 with a justification that economy-level
absence stays a human-review judgement. Expected effect ≈ +11 exact rows
(~+2.2pp) before any re-run; the remaining 7.2 misses (0->0.5, sectoral
over-match) are an extraction-calibration problem, tracked separately.

## 2026-07-22 — a ruled schedule reached the index as a number jumble

PyMuPDF's flat text layer reads a table cell-by-cell, so a retention /
penalty / tariff schedule arrived at the chunker as an unlabelled run of
numbers with the header->cell link gone — exactly the provisions where the
cell value carries the score (7.3 needs a SPECIFIC minimum retention period,
and "7 years" only means anything while it is still attached to its row).

Fix: `rag/tables.py` reconstructs each page's grid via `find_tables()` and
serialises it to Markdown under a `=== Table (page N) ===` marker; ingest
appends the blocks after the prose, so the chunker/embedder sees a real
table. Extraction is fail-open — an old PyMuPDF without `find_tables`, an
encrypted file, or one bad table yields fewer or zero tables, never a broken
ingest.

Lifting the helper out of `services/canvas_file_ingest.py` into `./rag`
exposed the other half of the bug: retrieval's `_low_substance` heuristic
demotes chunks that are short and carry no operative verb, and a schedule row
is both. Tables were being reconstructed on ingest and then buried behind
prose at query time. `looks_like_table` now exempts them, after the ToC check
so a ruled table of contents stays demoted.

## 2026-07-22 — retrieval could not find "section 46"

The RAG query path was pure dense cosine, which is weakest exactly where legal
retrieval is most demanding. A statutory identifier ("s46", "Act 854",
"section 125") is a near-arbitrary token, and MiniLM maps every such reference
into the same fuzzy neighbourhood. Measured on the live corpus: the query
"section 46" returned three chunks about exemptions and consent managers, and
never returned the actual s46 text at all.

Fix: a lexical arm (`chunk_tsv`, a STORED generated tsvector + GIN index on
document_chunks) fused with the dense arm by Reciprocal Rank Fusion in
`rag/hybrid.py`. RRF consumes only ranks, so cosine (~0-1, tightly bunched) and
ts_rank_cd (unbounded) combine without a normalisation constant that would need
retuning per corpus. After: "section 46" returns the real provision at rank 1,
while a pure-paraphrase query ("can personal data be transferred outside the
country?") returns byte-identical results — the lexical arm adds signal without
displacing the dense arm where dense is right.

Text-search config is 'simple', not 'english': the corpus spans 8 languages, and
stemming/stopword removal would damage the others while mangling the statutory
tokens the arm exists to catch. Known limit — 'simple' splits on whitespace, so
unsegmented scripts (ZH/TH/JA) contribute little lexically and those queries
keep their previous dense-only behaviour.

Both filters (country, document scope) are applied to BOTH arms; a filter that
reached only the dense arm would let the lexical arm leak out-of-scope rows, so
that has its own test. `score` stays cosine for every row — lexical-only hits
are joined back to their embedding — so min_score and the UI keep their meaning.
Databases predating the migration are probed once per process and degrade to
dense-only rather than erroring.

Writing the fusion tests corrected an assumption worth recording: at k=60 RRF
barely separates adjacent top ranks ("1st + 3rd" edges out "2nd + 2nd" by
~0.03%). RRF is a tie-breaker that stops one arm dominating, not a fine-grained
ranker — finer separation at the head is a reranker's job, which the query path
still lacks.
