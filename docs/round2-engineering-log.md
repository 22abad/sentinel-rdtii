# Round 2 engineering log — problems met, root causes, fixes

_Companion to `docs/round2-meeting-report.md` (the numbers). This is the story
behind them: every material problem hit while standing up the 12-pillar ×
7-economy pipeline, its root cause, the fix, and the verification. PR numbers
link every claim to code._

---

## 2026-08-03 — RUS 6.3: the evidence didn't exist in our file (b994d9b)

- **Symptom:** single-target replay of 6.3 on "our 152-FZ text" mapped fine in
  isolation, yet every pipeline run produced nothing — and a new focused
  backfill pass ALSO came back empty, silently.
- **Layer 1 — batch competition:** a law hinted for both 6.1 and 6.3 gets one
  batch extraction; the model routes the evidence to the best-fitting sibling
  and 6.3 starves. Fix: focused gap-backfill pass in run_corpus (single-target
  re-extraction for every still-empty hinted indicator; empty results now
  surface raw/rejected counts in warnings instead of vanishing).
- **Layer 2 — corpus currency:** the 6.3-hinted file was the 2006 ORIGINAL
  152-FZ. Art 18(5) data localization was inserted by 242-FZ in July 2014 —
  the provision literally did not exist in our text; the extractor was
  honestly right to find nothing. Fix: current consolidated redaction from
  the official pravo.gov.ru IPS (rdk=60, 134K chars; the publication PDF is a
  scan — Russian tesseract installed as the fallback path).
- **Layer 3 — exact-match shadow:** backfill STILL read a 12K file. The
  diagnostic warning (added in the same commit) named the culprit: the 6.1
  entry's curly-quoted law name `“On Personal Data”` matches the inventory
  string EXACTLY, so name resolution short-circuits before the
  largest-text-wins logic — and that 12K file is an ANNOTATION, not the law
  (its "quotes" are summary sentences). Fix: consolidated entry renamed to
  the same exact name; largest char_count now wins for every 152-FZ read.
- **Result:** P6 rerun = 9 provisions incl. 2× P6-I3; the P6-I1 rows now
  quote statute text instead of annotation prose.
- **Lessons:** (1) when an extractor "fails", first prove the evidence exists
  in the text you actually feed it; (2) an exact-name match is a stronger
  trap than a fuzzy one — it never reaches your tie-breakers; (3) silent
  empty results deserve a diagnostic path of their own.

---

## 2026-08-03 — one cell, three independent kill-layers (CHN 10.2) (001a0fb, 5c3e699)

- **Method:** `scripts/replay_one_cell.py` + direct `run_extraction` replays —
  peel the pipeline stage by stage on ONE failing cell instead of guessing.
  Each replay exposed the next bug once the previous one was fixed.
- **Bug 1 — prompt:** a catalogue has no "shall/must" sentence, so the model
  quoted the TITLE (14 chars, no article) and the missing-article gate dropped
  the row. Fix: catalogue-entry rule in build_prompt/build_batch_prompt
  (entry = the measure; entry number = article_clause).
- **Bug 2 — reflow:** PDF extraction hard-wraps Chinese mid-word (视\n频);
  the model silently repairs the word when quoting, so the quote fails the
  exact-substring verify. Fix: CJK wrap join in reflow_legal_text (第X条/章
  heading starts preserved). Benefits every Chinese corpus text.
- **Bug 2b — repair prompt:** after a heading-reject, the repair call knew
  nothing about catalogues and returned an empty quote — a SILENT skip (the
  corpus path records no rejection). Fix: catalogue rule in
  build_repair_prompt.
- **Bug 3 — validation:** `str.isupper()` is True for a caseless CJK quote
  whose only cased characters are a Latin entry code ("216501X") — the
  ALL-CAPS-heading heuristic hard-rejected a 92-char substantive provision.
  Same class hits any CJK/Thai/Lao quote embedding GB/ICP/374-FZ-style codes.
  Fix: heuristic now Latin-script-only.
- **Result:** run_extraction replay 0/3 → 3/3 stable mappings. Suite 891.
- **Lesson:** "no output" is not one bug. Replay the pipeline layer by layer
  and each silent gate confesses separately. Also: every text-quality gate
  written for English needs a caseless-script audit.

---

## 2026-08-03 — EAEU Treaty killed by a Round-1 rule that Round 2 outgrew (12b6c9b)

- **What happened:** RUS 11.2/11.3 sat in the gap list as EXTRACTION /
  CORPUS_QUALITY, yet the official inventory's source for both — the
  "Eurasian Economic Union Treaty" — was already in the corpus at 1.33M chars.
  scan_gate_misses.py (the 684-name ground-truth scan) showed the name still
  dropping after the 08-01 word-list extension.
- **Root cause:** two independent gates both killed it. (1) The statute-word
  list had no `treaty`/`agreement`. (2) `_OUT_OF_SCOPE_INSTRUMENT` — added in
  Round 1 with good evidence (13/26 SGP rows were FTA-chapter over-extraction)
  — blanket-drops `treaty|convention|protocol`. Right for FTAs; wrong for EAEU
  law, which has direct effect in member states (like EU regulations) and is
  what the official inventory actually cites for RUS 11.2/11.3.
- **Fix:** statute-word list gains `treaty|agreement`; narrow
  `_SUPRANATIONAL_DIRECT_EFFECT` carve-out (EAEU/EEC names only) on the
  out-of-scope gate. Regression test proves CPTPP/RCEP/FTA rows still drop.
  Suite 888 green.
- **Lesson:** an empirically-validated rule carries the date of its evidence.
  When the scope changes (new economies, new inventory), re-run the rule
  against the new ground truth before trusting it — same discipline as the
  word-list scan, which is exactly what surfaced this.

---

## 2026-07-31 (night) — auto_fix_corpus Wayback-garbage incident (caught by verify-before-presenting)

- **What happened:** the overnight corpus auto-fixer reported "50 fixed, 11
  failed". Spot-check of the byte counts showed 43/50 "fixes" were an IDENTICAL
  2,770-char page — the Wayback Machine's own UI shell ("Keep the news in the
  Wayback Machine", "Internet Archive logo"…), saved as "law text". wb_fetch's
  banner heuristic only rejected the shell in `mode=''`; the `if_`/`id_` modes
  returned the shell straight through with >200 chars, passing the length gate.
- **Real damage (precisely characterized):** only 11 cells got polluted manifest
  entries + garbage files (CHN 7.4/10.1/10.2/12.1/12.2, IND 8.4/10.1,
  RUS 4.9/5.7, LAO 5.4, THA 5.4 — all sha256 0518cc74…). The other 32
  garbage fetches hit "existing file larger, keeping" and were no-ops (file
  kept, manifest untouched — verified per-cell in the log). IDN fully clean.
  **Honest verdict: the run fixed ZERO cells and polluted 11.**
- **Fix:** `scripts/clean_wayback_garbage.py` — surgical: delete files matching
  the garbage sha256, drop their manifest entries, restore pre-incident entries
  from the Jul-28 backup where the old text still exists, otherwise return the
  cell to honest FETCH_GAP. Vaccine in `auto_fix_corpus.py`: `is_garbage_page`
  rejects the Archive.org UI shell at fetch AND at save.
- **DeepSeek exposure:** the gap-run batch read the polluted manifest for
  CHN 7.4/12.1/12.2 only; extraction gates reject non-statute UI text, CHN
  outputs to be audited post-run.
- **Lesson:** a fetcher's "success" count is meaningless without a content
  check; identical byte-counts across "different" documents are the tell.
  (Same family as the #309 name-vs-source class: the artifact exists, but it
  is not what its label says.)

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

## 2026-07-21 — Cross-model checker for generic-scored indicators (Maker/Checker)

A Maker/Checker design with our differentiator: the score stays deterministic
Python; the second model only
supplies a categorical fact. The error taxonomy put the largest remaining
mismatch family on P9-P12 over-scoring (official 0 → we said 1) — indicators
that fall through to scoring/generic.py, which has no independent gate (the
EligibilityVerifier is P6/P7-only).

New `agents/score_checker.py`: for a POSITIVE generic score only, a checker
model — blind to the extractor's features and score — re-reads the exact quote
against the official criterion text and returns the criterion it EXPLICITLY
satisfies (0 = principle/relevance). We keep min(extractor, checker). A
disagreement never drops the row: it lowers the score and flags for review.
No-op for bespoke 2/5/6/7 indicators, for already-zero scores, offline
fixtures, or checker failure (infra failure must never demote). Reuses the
pipeline provider by default; RDTII_CHECKER_PROVIDER selects a distinct model
for a true cross-model pass; RDTII_SCORE_CHECK=off disables. Per-run cache
keyed by indicator+normalised quote.

Round-1 offline output is unaffected: it is P6/P7 only (bespoke path).

## 2026-07-21 — curl_cffi impersonated fetch + SSO print endpoint (fixes the Round-1 blocker)

Diagnosed the WAFs that sank our Round-1 SGP discovery. The fix is a real
Chrome TLS fingerprint via curl_cffi `impersonate="chrome"` — no browser, no
proxy, no ja3 tuning. CDN
WAFs (sso.agc.gov.sg on CloudFront) filter on TLS fingerprint and 403 both
plain httpx and Playwright, but pass an impersonated client.

Live A/B (2026-07-21): today SSO does not block plain httpx (the Round-1
block was intermittent — WAFs weigh IP reputation/time), so curl_cffi is
insurance for the next block. But the SECOND finding is deterministic and
was the bigger bug: /Act/{code} lazy-loads provisions via Knockout JS and a
plain fetch yields only a ~1/8 SHELL (25K visible chars). The print endpoint
?ViewType=Print&PrintType=html&ProvIds=all-. server-renders the FULL body
(198K). ?WholeDoc=1 did NOT expand it.

New `_try_impersonated_fetch` (first HTTP rung in fetch_legal_content) fetches
via curl_cffi impersonate=chrome and rewrites SSO Act/SL URLs to the print
endpoint, with the existing body-integrity checks (legal signal, challenge
detection). End-to-end through the real pipeline: /Act/PDPA2012 now returns
186,327 chars of full statute (s25 retention + s26 cross-border present) vs
the old shell. Falls through to httpx / Playwright unchanged on any failure
or missing dep. Pure-function unit tests for the URL rewrite + extraction.

## 2026-07-21 — SGP discovery goes head-to-head (no third-party search engine)

Switched the Singapore SSO discovery adapter's HTTP client to curl_cffi
impersonate=chrome (falls back to httpx if the dep is missing). The adapter
already queried SSO's OWN search endpoint (/Search/Content?Phrase=) — SSO's
search, not a third-party engine — but plain httpx got WAF-shelled on TLS
fingerprint, so live search returned nothing and the adapter fell back to
fixtures every time. With the impersonated client the same endpoint returns
real results: a live query for "personal data protection / cybersecurity /
data retention" now yields 9 live SSO Act hits (PDPA, FSMA, MAS Act, Credit
Bureau Act, IMDA Act, …), retrieval_mode=live, zero fixtures.

End-to-end proof (DISCOVERY_SEARCH_BACKEND=none, --no-seed, --max-documents 8
— i.e. NO web search engine, NO seeds): the run pulled 15 candidate documents
straight from SSO (25 curl_cffi fetches through the print endpoint, including
FSA1993 234K + CA2018 193K — the exact acts the Round-1 playbook flagged as
"no fallback, don't touch"), correctly skipped the out-of-scope ASDEA
agreement, and produced 10 rows / 3 NEW (PDPA s44(d), IMDA Act s72(1)(b),
MAS Act s28(1)) with no third party in the loop. The block that sank Round-1
SGP discovery is beaten by our own code. (Full NEW harvest needs the doc cap
lifted + P6 queries; this run proves the plumbing.)

## 2026-07-21 — Universal body-integrity gate on the fetch ladder (Dong's insight)

Dong's framing: discovery robustness is not a per-country problem, it's ONE
sequential fallback ladder that must work for every country's portal. The
ladder already largely exists in fetch_legal_content —
curl_cffi → httpx → Playwright(×3) → per-domain alternates → Wayback →
Google cache. The real gap was that the gate deciding "did this rung succeed?"
was inconsistent: the cheap HTTP rungs checked legal-signal + length, but the
Playwright rung shipped ANY content >5KB even if it was a navigation shell or
a 200-OK banner — so a shell was returned as success and the archive rungs
below it never ran.

Added `_is_real_legal_content(text)` — a single body-integrity gate (min
length + legal signal + not an error/challenge/WAF banner) — and applied it at
the Playwright rung: a shell now raises and escalates down the ladder instead
of being mapped. Same gate the curl_cffi/httpx rungs already use, so every
rung now judges success identically. This is what makes the ladder behave the
same for SG (WAF banner) and, say, a CN portal that 200s an error page. 6 unit
tests; full suite 686 green.

## 2026-07-21 — R2 discovery country-by-country: Thailand + Laos via ODM CKAN

Dong's plan: discovery is per-country (each portal differs), so verify one at a
time. A GitHub hunt across all 7 R2 countries surfaced the portal landscape;
first quick win shipped.

Reachability recon (curl_cffi): Russia pravo.gov.ru = geo-blocked from non-RU
IPs (25s connection timeout — has a clean official API `/api/Documents` with
eoNumber id-discovery per mikhashev/law7, but unreachable without RU egress).
Thai ratchakitcha = Cloudflare 403. Reachable + structured: Open Development
Mekong CKAN, Indonesia peraturan.bpk.go.id, Mongolia legalinfo.mn, India Code.

Shipped: `MekongCkanAdapter` (Thailand + Laos). ODM is a CKAN 3.x catalogue that
republishes the official gazette PDFs with the official source URL preserved
per law (`odm_laws_source`) — a reachable mirror of official text, not a search
engine. Query: `package_search?q=<pillar>&fq=organization:<country>-organization
AND type:laws_record`; drops drafts/repealed by `odm_laws_status`; returns the
gazette PDF as the fetch target with official provenance in `raw`. Live: a
Thailand P6/P7 query returns PDPA B.E. 2562 + Cyber Security Act B.E. 2562 with
PDFs, no search engine. Wired into sources.yaml (priority 110, above the
Cloudflare-blocked ocs.go.th and DuckDuckGo). 4 unit tests (mocked CKAN);
full suite 690 green.

Landscape for the remaining R2 countries (agent-verified endpoints, next up):
India = browse-index `/handle/123456789/1362/browse?type=shorttitle&offset=N` →
handle page → `/bitstream/.../*.pdf` (solves the bitstream-id discovery nobody
automated); Indonesia = official `api-jdih.perpusnas.go.id` Bearer JSON API;
China = flk hidden JSON `/api/?type=flfg…` + `/api/detail` (WAF-gated) or the
`lawtext/law-flk-vol1` bulk corpus; Mongolia = Playwright crawl of
legalinfo.mn cate=27; Russia = official API but needs RU egress.

## 2026-07-21 — R2 discovery: Indonesia via peraturan.bpk.go.id

Second R2 country. Indonesia's official JDIHN JSON API (api-jdih.perpusnas.go.id)
needs a registered Application Key (401 "Application Key tidak ditemukan"), so
it's gated. peraturan.bpk.go.id — the most complete official DB — is Cloudflare-
protected but a Chrome TLS fingerprint (curl_cffi) clears it. New
`IndonesiaBpkAdapter` does a two-step scrape of the portal's OWN search:
/Search?keywords= → /Details/<id>/<slug> links → each Details page → title +
in-force status + /Download/<fileid>/*.pdf. Drops revoked ("Dicabut") /
not-in-force instruments; returns the official PDF as the fetch target. Live: a
P6/P7 query returns UU No. 27/2022 (the PDP Law) + Permenkominfo 20/2016 with
direct PDFs, no search engine. Wired into sources.yaml priority 110. 3 unit
tests; full suite 693 green.

## 2026-07-21 — R2 discovery: India via India Code, solving bitstream-id discovery

Third R2 country (fourth economy incl. Laos). India Code is a DSpace repo with
REST/OAI disabled (404). Hard-coding bitstream ids is brittle — new Acts break
it — and "discover the id for a given law" looked unsolved. It isn't: the portal's own
`simple-search` results table carries, per Act, the handle id, which resolves
to the official bitstream PDF. IndiaCodeAdapter: GET /simple-search?query= →
parse the results table (short-title cell + View→/handle/<id>), then GET
/handle/123456789/<id> → first /bitstream/.../*.pdf. Live: a "personal data
protection / information technology" query returns the Digital Personal Data
Protection Act 2023 (handle 22037 → a2023-22.pdf), the IT Act 2000, and the
Aadhaar Act — official PDFs, no search engine, no hard-coded ids. Wired into
sources.yaml (was search_engine/DuckDuckGo). 3 unit tests; full suite 696 green.

R2 discovery scorecard: Thailand + Laos (CKAN), Indonesia (BPK), India (India
Code) shipped. Remaining: China (flk hidden JSON API, WAF-gated), Mongolia
(legalinfo.mn Playwright), Russia (official API but geo-blocked, needs egress).

## 2026-07-21 — Deterministic scope-override guards

The Round-2 error taxonomy's largest residual family is over-scoring official-0
cells where the extractor finds a genuine measure that keyword-matches an
indicator but is out of that indicator's official scope (106 such rows across
the 7-economy benchmark). Neither the generic scorer nor the cross-model
checker catches these — both see a real restriction. Added a deterministic
`enforce_indicator_rules` guard, limited to methodology-EXPLICIT cases to avoid
regressions.

New `scoring/scope_overrides.py`: (1) 9.1's own exception — blocking of
internationally-agreed illegal / child-pornography content is not a 9.1 measure
→ 0; (2) product-health/vice control laws (tobacco, alcohol, narcotics,
gambling, firearms, pornography) are not digital-trade measures → 0 for pillars
9/10/12 (pillars 6/7 deliberately excluded — a product law can still carry a
real data clause). Checks law name AND verbatim (the law name isn't resolved at
scoring time in the eval path). Only ever lowers to 0; every drop annotated.
Wired into the orchestrator before the LLM checker (deterministic, no extra
call). 8 unit tests; full suite 704 green.

Honest measurement: on IND (isolated, checker off) the tobacco Cigarettes Act
9.3 row went 1.0 → 0 → exact match, exactly the documented trap; over-scores
12 → 11. Single-economy exact-rate held at 49.3% — the +1 is inside LLM
sampling noise for one run. Real value is a deterministic, defensible safety
net (fixes the tobacco/alcohol/porn traps across all 7 economies, ~6-10 rows)
and a guard as we open pillars 8-12 where cross-domain keyword collisions
multiply — not a large single-number mover.

## 2026-07-21 — R2 end-to-end verification: India + Thailand pass, Indonesia needed query localization

Ran the three shipped R2 discovery adapters end-to-end through main.py
(--no-seed, DISCOVERY_SEARCH_BACKEND=none — no seeds, no web search engine):
- India: 22 rows, P7-I1..I5, DPDP Act 2023 + IT Act 2000 (see prior entry).
- Thailand: 7 rows, P7-I4/I5 — PDPA B.E. 2562 + Constitution mapped from Thai
  text via the Mekong CKAN adapter. Non-English chain works.
- Indonesia: 0 rows first pass. Root cause: the query builder emits ENGLISH
  pillar queries ("personal data protection act"), but peraturan.bpk.go.id
  indexes Bahasa Indonesia only — English terms returned import/education
  regulations, which mapped to nothing eligible. (Thailand escaped this because
  ODM CKAN carries English metadata.)

Fix: `_localize_query` in the Indonesia adapter maps the English P6/P7 concepts
to Bahasa Indonesia search terms (personal data protection -> perlindungan data
pribadi, cross-border -> transfer data pribadi ke luar negeri, cyber -> keamanan
siber, retention -> penyimpanan dokumen elektronik, …), dedup'd. With it the
adapter returns UU 27/2022 (PDP Law) + Permenkominfo 20/2016. 1 unit test; full
suite 705 green. General lesson: non-English portals that index local text (CN,
MNG, RU later) each need local-language query terms — the query builder's
English output is not enough on its own.

## 2026-07-21 — Combined accuracy measurement: 3 economies up 8-13pp

Ran IDN/THA/MNG with all of today's accuracy work ON (7.1/7.2 fall-through fix,
cross-model checker, scope overrides) vs the committed 2026-07-16 baseline:
- IDN: 36% (32/88) -> 47.9% (80/167). +12pp, but corpus also expanded (88->167
  rows), so this is corpus + accuracy combined.
- THA: 53% (56/105) -> 61% (64/105). +8pp, corpus UNCHANGED.
- MNG: 55% (41/75) -> 68% (51/75). +13pp, corpus UNCHANGED.

THA and MNG evaluate the same rows as the baseline, so their +8/+13pp is a real
accuracy gain from the deterministic fixes, not coverage and beyond single-run
LLM sampling noise (+7-10 exact each). The earlier single-economy IND runs read
as "within noise" because IND happened to be insensitive to these particular
fixes; the cross-economy consistency confirms the fixes work. Honest caveat:
some LLM sampling variance is folded in — these are single runs, not averaged.

## 2026-07-21 — India corpus backfill result (coverage +17 rows, +8 exact)

Ran fill_india_corpus.py (india_code adapter → current bitstream PDFs) then
re-eval'd IND: 75 → 92 rows evaluated (+17, previously auto-0 no-text rows now
scored from real text), 37 → 45 exact (+8), rate held at ~49%. The 5 filled
Acts each cover several indicator rows (DPDP Act alone spans 6.1/6.3/6.4/
7.1/7.4/7.5). India's flagship data law now scores correctly (DPDP 7.4/7.5/7.1
exact) instead of 0-by-default — the biggest value for the actual submission.

Honest note vs IDN's +12pp: the RATE moves only when the newly-covered laws
score well. IDN's expansion added rows that mapped cleanly; India's mix (IP
Acts P4, cross-border P6) scores at the average, so coverage/absolute-correct
rose (+8) while the rate stayed flat. Lesson: corpus backfill pays off most
when it targets the core data/cyber laws of each economy, not just any gap.

## 2026-07-21 — Cross-language NEW/KNOWN reconciliation (fixes Indonesia's all-NEW)

The multi-country harvest tagged all 43 Indonesian rows NEW — a credibility
bug: the Indonesia adapter returns native titles ("UU No. 27 Tahun 2022")
while the baseline lists English ones ("Law No. 27 ... 2022"), so normalized
names never matched and every rediscovered baseline law read as a NEW find
(over-claiming the 20-point NEW bonus).

Fix: `law_number_key()` extracts a language-neutral "<number>/<year>" identity,
and `known_law_index()` adds `(economy, "#<key>")` — but ONLY for keys that map
to exactly one distinct baseline law in that economy (`_unambiguous_number_keys`,
counting distinct normalized names, so a law repeated across indicator rows
still counts once, while a number reused by different ministries is dropped).
is_known_law falls back to the number key when the name doesn't match. UU
27/2022 now reconciles to KNOWN; a fabricated number stays NEW. Residual risk:
a genuine NEW law coincidentally sharing an unambiguous number+year is tagged
KNOWN — conservative (under-claims NEW, never over-claims). 3 tests; suite 708.

## 2026-07-21 — Full error taxonomy → prioritized next-fix roadmap

Across 634 evaluated rows (54% exact) the residual errors, ranked:
- **Missed (official>0, no evidence) — 7.3 leads (14), then 6.4(8), 9.1(7),
  2.3(6).** 7.3 (data retention) misses are extraction RECALL: the law is often
  in the corpus (e.g. Telecom Act 2023) but the specific minimum-retention
  clause isn't surfaced from the long statute. Hard — needs retention-clause
  targeting, not a quick fix.
- **Under-scored with evidence — 2.3 leads (10), all official 1.0 -> we 0.5.**
  Diagnosed: 2.3 criterion 1 includes "OR more than one measure under category
  (2)"; a procurement law with MULTIPLE local-content/performance measures
  should escalate 0.5 -> 1, but our extractor picks one measure and stops at
  0.5. Fixable via a measure-count escalation (medium effort, ~+10 rows).
- **Over-scored — 7.1(6)/7.2(5) partly fixed; 9.1/10.1/12.7/10.4 remain**
  (cross-domain scope; the scope_overrides guard covers the product-domain
  subset).

Backfill quality: after wiring _best_hit + a strong-match requirement, the tool
now refuses weak matches (Companies Act 2013 stays auto-0 rather than being
mis-filled with a Telangana/West Bengal state Act) — corpus stays clean.

Next-fix priority by ROI: (1) 2.3 measure-count escalation (concentrated,
scorer-side); (2) targeted retention-clause extraction for 7.3 (biggest miss,
harder); (3) translation-level cross-language name matching (Indonesia NEW/KNOWN
residual). CN/RU coverage stays blocked by environment.

## 2026-07-21 — HEADLINE: full 7-economy benchmark 50.2% -> 55.7% exact (+5.5pp)

Re-ran all seven R2 economies with today's cumulative work (corpus expansion +
india_code backfill + 7.1/7.2 fall-through fix + cross-model checker + scope
overrides). Combined vs the committed 2026-07-16 baseline:

  Rows evaluated 500 -> 670 (+34% coverage)
  Exact matches  251 -> 373 (+122)
  Exact rate     50.2% -> 55.7% (+5.5pp)

Per economy: CHN 47->60, IDN 36->48, MNG 55->68, LAO 60->68, THA 53->61 (all
up); IND 49->49 flat; RUS 53->48 down. IND/RUS "held/fell" is a denominator
effect — more (harder) rows evaluated, but absolute exact still rose (IND
31->45, RUS 31->40). Same-corpus economies (THA/MNG/LAO) rose 8-13pp, which is
pure accuracy gain (their corpus is unchanged), confirming the fixes work
beyond single-run noise. Evidence rate 70.2% -> 59.9% is likewise a denominator
effect (absolute evidence-backed rows 351 -> ~401). Honest caveats: single run
(LLM sampling variance folded in); the IDN/IND corpus changed, so their delta is
coverage + accuracy combined, not isolated.

## 2026-07-21 — Measured the 2.3 escalation, REVERTED it (honest negative result)

Built economy-level escalation for the 9 "more than one category-2 measure ->
full score" indicators (scoring/aggregation.py, methodology-derived) and wired
it into the eval. Isolated deterministic effect across 7 economies:
IND +5, THA +2, RUS +1, **CHN -6** = net +2 only. Root cause of the CHN
regression: counting half-score PROVISIONS conflates "one measure spanning
several provisions/laws" (China's data-localization 6.1/6.2 — one 0.5 measure
repeated) with "several distinct measures" (India's procurement 2.3 — genuinely
different rules). The rule is only safe with distinct-measure-TYPE detection,
which the extractor doesn't provide. Per our discipline (measure, and drop what
regresses), the eval wiring is reverted; the aggregation module + 7 unit tests
stay as a correct, documented building block for when measure-type extraction
exists. The 7.3 feature-spec synonym broadening (retain/preserve/maintain/keep
+ explicit minimum period) is kept — low-risk recall aid.

## 2026-07-21 — Deepen RAG: language-aware retrieval (6 of 7 R2 economies are non-English)

The BM25 retriever tokenized ASCII only, so a Chinese/Russian/Indonesian/Thai
statute produced an empty query and fell back to a blind prefix — i.e. RAG did
nothing for 6 of the 7 R2 economies. Deepened: (1) a unicode tokenizer — word
runs in any script (Cyrillic/Thai/Latin) plus CJK character bigrams (Chinese
has no word boundaries); (2) select_relevant_text takes country_code and adds
the economy's LOCAL_TERMS to the query, wired through the CLI pipeline and the
evaluator. Verified: a Chinese statute with the retention clause buried past
the cap is NOT retrieved by the English query but IS with the CHN local terms.
Also fixed CHN 7.3 local terms — the actual Cybersecurity-Law verb is 留存
(retain), which the terms were missing (had 保留/保存). 3 new tests; suite 722.

## 2026-07-21 — RAG measured: RUS +2 exact/+4 evidence, IND 7.3 recall 6/8

Language-aware retrieval vs baseline on the large-doc non-English economies:
RUS 40/84 -> 42/84 (+2 exact, evidence 43->47 — the Cyrillic tokenizer + local
terms retrieve from large Russian statutes that blind-truncation dropped);
THA 64/105 -> 63/105 (flat, within single-run noise; many Thai docs are under
the 60K-CHAR cap once UTF-8 multibyte is counted, and Thai local terms are
sparse). IND (English, BM25): 7.3 recall rose to 6/8 rows evidence-backed, 5
exact — directly the retention-clause miss the taxonomy flagged. Net benchmark
effect is modest (retrieval only touches >cap docs and the recall gain competes
with LLM variance), but the capability is real and demonstrable, and the two-
path architecture (dense web workbench + sparse language-aware CLI) is a
genuine highlight. Follow-ups: richer local-term coverage per economy;
optional dense-BM25 RRF fusion when a lean embedding model is acceptable.

## 2026-07-21 — Enrich local-language query terms (IDN + RUS now 9/9 P6/P7)

Local terms drive both discovery (adapter search) and RAG retrieval on
non-English statutes, but coverage was sparse (IDN 5/9, RUS 7/9 of the P6/P7
indicators). Filled the gaps — IDN 6.1/6.2/6.3/7.4, RUS 6.3/7.4 — with legal
vocabulary VERIFIED to appear in the fetched baseline corpus (grep-checked, so
no repeat of the CHN 留存-vs-保留 miss; dropped "хранение персональных данных",
which appears 0× in the RUS corpus). Verified end-to-end: on the 329K Indonesian
PDP Law the data-centre clause ("pusat data") is NOT retrieved by the English
query but IS with the IDN 6.3 terms. Suite 722. CHN already 9/9; MNG/LAO stay
sparse (blocked/no adapter, obscure scripts) — future work.

## 2026-07-21 — Silent corpus corruption: IDN P6 run_corpus 0 → 19 rows

**Symptom.** `run_corpus('Indonesia', 6)` produced ZERO submission rows —
`documents_processed=9`, `provisions_mapped=0`, no warnings. Every one of the 9
P6 laws (incl. the flagship Law No.27 PDP 2022, mapped to 6.1/6.3/6.4) returned
0 extraction mappings. First suspect was retrieval budget (a 150K vs 60K cut had
earlier changed a 6.4 quote from score 0.0 to 1.0), then merged-query dilution
(fixed the retriever to allocate the char budget per-indicator so a term-dense
indicator can't crowd another's clause out — real improvement, kept). Neither
moved the needle: still 0 rows.

**Root cause — the corpus text on disk was the WRONG LAW.** The manifest
recorded the PDP law at `char_count=329056`, but the on-disk `.txt` was 18617
chars of a completely different 2025 witness-protection regulation. A
manifest-vs-disk audit found **34 IDN corpus files truncated to < 50% of their
recorded char_count** (other 6 economies clean). Mechanism: `fill_corpus.py`
treated only manifest records with `status=="cached"` as already-present, but
`build_round2_corpus.py` writes originals as `status=="ok"` — so the backfill
considered every original law "missing", re-searched bpk.go.id, and OVERWROTE
the good full text at the same slug path with a (frequently wrong, always
shorter) search hit. Extraction on the wrong text correctly finds no P6
provisions → 0 rows. No fabrication ever occurred (rule 5 held: the wrong text
just yields nothing), but the corpus was silently poisoned.

**Fix — three layers.**
1. `tools/restore_corpus.py` (new): manifest-vs-disk integrity guard + repair.
   Detects corruption by sha256 mismatch AND size < 50% of char_count, re-fetches
   from the recorded good `url_used`, and accepts only non-truncated text
   (sha256/char_count exact, or ≥70% of char_count from the same URL — the
   corruption is always <50%, so this can't re-accept a mis-fill). `--check`
   audits without fetching. Restored 12/34; the flagship PDP law is back at 329K.
   The other 22 have stale `url_used`s that now return truncated pages — left
   FLAGGED, never patched with wrong text.
2. `fill_corpus.py` root-cause fix: treat `status in ("ok","cached")` as present
   (not just "cached"), and never shrink an existing file (skip when the fresh
   fetch is smaller than what's on disk). Defense in depth against re-poisoning.
3. `run_corpus` manifest read: include `ok` records (not only `cached`), and on
   duplicate law_name keep the record with the largest char_count so a short
   corrupt entry can't shadow the good full text.

**Verified.** `run_corpus('Indonesia', 6)`: **0 → 19 P6 rows** across the 9
restored laws. Retriever suite green (per-indicator budget). Remaining IDN
corruption is now a visible, tested condition (`restore_corpus --check`), not a
silent 0. Follow-up: recover the 22 via the indonesia_bpk adapter's CURRENT
Details URL rather than the dead `url_used`.

## 2026-07-22 — The offline generator was silently running on a dead Ollama

**Symptom.** `python main.py --from-corpus --pillar all` crawled — a single
economy's P6,7 pass had not finished after an hour, and 7 economies in parallel
made it look throughput-saturated. A standalone `run_extraction(..., resolve_provider('deepseek'))`
on the same 329K law took **101s** (128 calls). Same work, wildly different time.

**Root cause.** `.env` sets `RDTII_LLM_PROVIDER=ollama` (the key-free judge
default). `main.py` without `--provider` resolves to Ollama at
`http://localhost:11434`, which was NOT running. Every batch extraction failed
with `Connection error`, fell back to per-indicator, and each fallback re-hit
the dead endpoint — so the pipeline spun on connection failures + retries
instead of doing work. The parallel "saturation" was 7 processes hammering a
dead socket, not a real throughput ceiling.

**Fix.** Pass `--provider deepseek` explicitly for the reproducible offline
generation. With DeepSeek, RUS P6,7 finished in **~3 minutes** (9 provisions),
zero 429s, 7 economies in parallel — i.e. the full 12-pillar × 7 offline
submission is entirely feasible; it only ever looked infeasible because of the
provider default. Lesson: when an LLM run is mysteriously slow, check WHICH
provider actually served the calls before assuming a rate/throughput wall.
Follow-up worth considering: have `--from-corpus` warn (or auto-skip) when the
resolved provider is an unreachable localhost Ollama, so a judge running the
default doesn't hit the same silent crawl.

## 2026-07-22 — Where the submission's headroom actually is (recall, not fetch)

With the full 12-pillar × 7-economy submission generated (663 rows, all-KNOWN,
97.1% verbatim-grounded), the honest completeness metric is **official
scorable-cell coverage: 132/229 non-zero cells (57.6%)**. Diagnosing the gap on
the lowest economy (RUS, 16/34) is instructive: **all 18 uncovered non-zero
cells HAVE local corpus text — zero fetch gaps.** So the remaining headroom is
**extraction recall**, not missing data: the statute is present and mapped by
the official inventory, but the pipeline surfaced no submittable provision for
that indicator (classifier/extractor recall, or a provision mapped to an
adjacent indicator — e.g. RUS 6.3 server-localization evidence landing under
6.1/6.2). This is the right next lever, but it is a precision/recall trade-off
that wants a human in the loop (loosening the eligibility/formal-submission
gate raises recall at the cost of the teacher-feedback precision bar), not an
overnight autonomous sweep. Documented here as the deliberate next step rather
than chased blind. NOT a corpus/fetch problem, NOT a provider problem — both of
those were tonight's fixes and are resolved.

## 2026-07-22 — NEW-law discovery: proven for IDN, per-portal hardening needed

Requirements confirm **20 Stage-2 points for discovering evidence BEYOND the
sample kit**; our all-KNOWN corpus submission earns 0 of them, so this is the
single biggest scoring gap. Ran `main.py --no-seed` (pure live discovery) on the
Round-2 economies to test the capability:

- **IDN — works.** Capped (`--limit 12 --max-documents 6`), it surfaced **4
  in-force laws beyond the baseline (18 NEW rows)** — BSSN (national cyber agency)
  regulations off peraturan.bpk.go.id via the curl_cffi adapter. *Caveat:* all 4
  mapped to 7.2 and are cyber-TRAINING regulations — likely off-topic for
  "cybersecurity framework" and a legal-review lead, not clean submission rows.
- **IND — 0 rows.** The india_code discovery path found/extracted nothing for
  P6,7. Different failure mode; needs adapter debugging.
- **THA — dead-end.** ocs.go.th searched with ENGLISH queries → "no results";
  needs Thai-language query localization (same fix pattern as IDN bpk's
  `_localize_query`).
- **Fetch bottleneck (all):** the default `browser_mode="auto"` tries Playwright
  first; peraturan.go.id PDFs time out at 60s×3 = 180s/doc and stall the run.
  `--max-documents` caps the damage; a real fix is HTTP/curl_cffi-first fetch for
  known-PDF portals, Playwright only as fallback.

**Conclusion:** the capability is real (IDN proves independent NEW finds are
reachable) but **not yet reliable or clean across portals**. Reaching the 20
points is a *scoped* effort — per-economy query localization + HTTP-first fetch +
a relevance gate so training/tangential regs don't map in — not an overnight
toggle. Matches the standing "discovery 总出问题" pattern. Next-task, not a
tonight fix.

### NEW-discovery per-economy blocker map (2026-07-22, actionable)

Diagnosed each Round-2 economy's discovery path (`discovery/sources.yaml` +
direct adapter tests). This turns "discovery is flaky" into specific fixes:

| Economy | Primary adapter | Status | Fix needed |
|---|---|---|---|
| IDN | indonesia_bpk (curl_cffi) | ✅ WORKS — banked 4 NEW laws / 18 rows | relevance gate (all mapped to 7.2, cyber-training regs likely off-topic) |
| IND | india_code | ❌ 0 hits — indiacode.nic.in TIMES OUT (30s, 0 bytes) today, worked 7/21 | EXTERNAL: site down/slow/IP-blocked; needs retry+cache, not a code fix |
| THA | mekong_ckan + thailand_ocs | ❌ ocs searched with ENGLISH → 0 | add Thai `_localize_query` (copy IDN bpk pattern); test mekong_ckan CKAN JSON |
| LAO | mekong_ckan | ⚠️ untested | verify CKAN JSON path |
| CHN | china_flk | ⚠️ untested | verify flk.npc.gov.cn reachable + parse |
| MNG | search_engine only | ❌ no dedicated adapter | DDG-only; needs a legalinfo.mn adapter, or SerpApi |
| RUS | search_engine only | ❌ no dedicated adapter + geo-block | pravo.gov.ru adapter or SerpApi; geo-blocked |

**Cross-cutting blockers:**
1. **DDG rate-limited** — `SERPAPI_API_KEY` is empty in `.env` (was present Jul 19),
   so every economy without a working dedicated adapter falls to DuckDuckGo,
   which bot-challenges our IP after heavy use. A SerpApi key unblocks MNG/RUS/
   fallbacks immediately (dev-time only — key-free DDG stays the judged default).
2. **Playwright-first fetch** — `browser_mode="auto"` tries Playwright (60s×3 =
   180s/doc) before HTTP; slow PDF portals (peraturan.go.id) stall the run.
   `--max-documents` caps it; real fix = HTTP/curl_cffi-first for known-PDF hosts.

**Recommended sprint order (highest ROI first):** fix india_code parse (IND,
English, tractable) → Thai localization (THA) → HTTP-first fetch → relevance gate
→ MNG/RUS adapters or SerpApi. Each working economy = more of the 20 NEW-discovery
points. Good candidate to split with Abel (crawler owner).

**Key realization (2026-07-22):** most discovery blockers are EXTERNAL and
intermittent — indiacode.nic.in times out today but worked yesterday; DDG
bot-challenges our IP after heavy use; RUS is geo-blocked. These are not code
bugs; robust discovery needs retry+backoff, a fetch cache, and a SerpApi
fallback for the DDG-dependent economies. The single highest-leverage unblock
is a **SerpApi key** (currently empty in `.env`) — it bypasses the DDG
rate-limit for every economy lacking a working dedicated adapter. Dev-time only;
the judged deliverable keeps the key-free DDG default.

### Key-free search: DDG-lite + curl_cffi (delivered) + multi-tier plan

**Delivered (committed):** `html.duckduckgo.com` bot-challenges heavy-use IPs
(HTTP 202); swapped the backend to `lite.duckduckgo.com` POSTed with a real
Chrome TLS fingerprint via curl_cffi. Verified returning real official URLs on a
fresh IP — India (indiacode.nic.in DPDP PDF, meity.gov.in), Mongolia
(legalinfo.mn — the official portal MNG had no adapter for), Russia. 100%
key-free (lite endpoint + curl_cffi). +2 tests, suite 730.

**Honest limitation found:** under a *marathon* of queries (a full multi-economy
discovery run × tonight's testing), even the lite endpoint eventually 202s our
specific IP — it is an IP-reputation/volume limit, not a code block, and
recovers with time. A judge running the tool fresh will not hit it. For
production robustness under load the right pattern is a
**multi-tier search fallback**: lite-DDG → Bing HTML → Mojeek → direct official-
portal adapter, each tried until one returns, with per-host politeness delays
(RateLimiter) to avoid triggering the challenge in the first place. Scoped
next-step; NOT built tonight to avoid worsening our rate-limited test IP.

**Net for the 20 NEW-discovery points:** the key-free search path is unblocked
and proven (IDN banked 4 in-force NEW laws / 18 rows). Reliable end-to-end
banking across all 7 economies still needs, per the blocker map: multi-tier
search + per-portal fetch (JS portals like legalinfo.mn fail the body-integrity
gate) + per-language extraction. A scoped sprint, well-mapped, good to split
with Abel.

### Discovery honest-yield after key-free + matching fixes (2026-07-22)

Two wins landed this session: (1) **key-free multi-tier search** — DDG Lite +
curl_cffi, with a **Bing fallback** (base64url-decode of bing.com/ck/a?u= click
redirects) as `MultiTierSearchBackend`; proven end-to-end (India discovery
0 → 23 rows via Bing while our DDG IP was rate-limited). (2) **novelty matching
hardening** so discovery doesn't over-claim: strip authority prefixes
("Government of India,"), leading articles, leading serial artifacts ("1 The …").

**Honest re-judge of the raw NEW counts after the matching fixes:**
- IND: raw NEW 10 → **genuine NEW 3 rows / 1 law** (Aadhaar Act) — the other 7
  were the IT Act, a baseline law that had been mislabelled NEW.
- IDN: raw NEW 18 → **genuine NEW 17 rows / 3 laws** (BSSN cyber regs) — real
  finds, but all mapped to 7.2 and cyber-TRAINING in nature, so a relevance gate
  is still needed before counting them for the cybersecurity-framework indicator.

**Takeaway:** the key-free discovery pipeline works and no longer inflates
discoveries with disguised baseline laws (claiming those would look worse to
judges than an honest count). Banking a solid pile of *genuine, on-topic* NEW
laws for the 20 points is now a matter of (a) broader discovery runs once our
test IP's rate-limit cools, and (b) a topic-relevance gate — a bounded scoped
task, on solid foundations.

### Embedding/hybrid RAG: built + data-tested; not the accuracy lever here (2026-07-22)

Dong asked for embeddings/RAG, so I tested it properly instead of assuming.

**Overturned the old assumption.** The CLI stayed BM25-only because
paraphrase-MiniLM embedded RU/TH/ZH as near-noise. A MODERN multilingual STATIC
embedding — **model2vec** (`minishlab/M2V_multilingual_output`, pure-numpy, NO
torch, ~30-100MB) — gives real cross-lingual signal: relevant-vs-irrelevant
cosine gaps EN 0.18, **RU 0.38**, ZH 0.07. So dense IS viable dependency-light.

**Built it.** `select_relevant_text` now fuses per-indicator BM25 with a dense
ranking via RRF when `RDTII_RETRIEVAL=hybrid` (opt-in; default BM25 so judges
need no model download). Tested, suite 737.

**But A/B says it doesn't move accuracy on THIS corpus.** RUS P7, bm25 vs
hybrid: identical (10 rows, 3 evidence, 2 exact, MAE 0.7 both). Root cause:
retrieval only engages for docs over the 60K cap, and **only 1 of 7 RUS-P7 docs
is that big** — the other 6 are fed whole, so hybrid==bm25 trivially. Corpus-
wide only ~30% of docs exceed the cap, and of the recall-miss cells just 13/64
are retrieval-limited (51 are extraction-limited). **Confirmed with data what
the recall diagnosis implied: retrieval isn't the bottleneck, extraction is.**

**Takeaway:** the hybrid capability is real, dependency-light, and a legit
demo/pitch asset ("modern multilingual embeddings, key-free, no torch"), but it
is NOT the lever for the accuracy/coverage gap — that's extraction/classification
quality. Kept opt-in so it never regresses the default. Honest negative result,
not hidden.

### The real accuracy ceiling: 58% of corpus texts aren't statutes (2026-07-22)

Chasing the extraction-recall gap (the 51 "extraction-limited" recall-miss
cells) led to the actual root cause. Classifying every corpus text as
STATUTE vs SUMMARY/STUB/THIN (`restore_corpus.py --quality`):

**Only 208/484 texts (42%) are the primary statute.** The other 276 (58%) are
law-firm summaries, fetch stubs (<3K), or thin fragments — text a judge's run
CANNOT extract a verbatim provision from. Per economy statute-share: LAO 72%,
MNG 65%, CHN 55%, RUS 52%, THA 51%, IND 36%, **IDN 18% (94 summaries)**.

Concretely: the MNG "Law on Personal Data Protection" corpus text is a law-firm
client alert ("On 17 December 2021 the Parliament passed … will establish …"),
not the statute; China's PIPL is a 1K stub of a very long law. Extraction
correctly yields nothing — the provision isn't in a summary. So of the 51
extraction-limited recall-misses, ~81% are corpus-quality (summary/stub/thin),
only ~19% are genuine extractor misses.

**Reframes the whole accuracy story:** the tool extracts *well* from real
statutes (97.1% verbatim grounding), and 57.6% official-cell coverage is
actually strong given that fewer than half the corpus texts are extractable
statutes. The lever for the coverage gap is **corpus quality — re-fetch the
primary statute for the 276 non-statute texts** — a data-acquisition problem
(detectable now via `--quality`, tractable per-portal), NOT prompt-tuning and
NOT retrieval. Extraction/classification is *not* the bottleneck the recall
numbers made it look like.

### Quality-hardening pass (2026-07-22)

Reviewed the pipeline against the qualities a reviewer would stress-test —
verification, grounding, cost transparency, provider independence — and closed
the gaps:
- **Blind-verifier override ledger**: we already run a blind cross-model checker
  on positive generic scores; added an override-rate ledger + end-of-run print.
  **Measured China P9-12 = 29% override** — a real quality metric ("nothing ships
  unverified, and here's by how much").
- **Byte-exact grounding hard gate**: confirmed we ALREADY hard-reject non-verbatim
  quotes (`prepare_extraction_with_repair` → `status:reject` after repair
  exhausts) — grounding is enforced at extraction, not a post-hoc measure.
- **Cost ledger**: added a cumulative run-total (calls/tokens/$; India P11 =
  $0.0254) on top of the existing per-pillar line, so deployment cost is reported
  transparently.
- **Open-weight swap + failover**: confirmed we already have `--provider ollama`
  (key-free open-weight) + `RDTII_LLM_FALLBACK_PROVIDER` FallbackProvider — the
  tool runs fully key-free and survives a provider outage.
- Deferred (low ROI for now): adversarial refuter on NEW rows (genuine-NEW yield
  is only ~4 laws, so the gate rarely fires today).

Net: grounding, blind verification, cost transparency, provider-swap and test
depth (740) are all in place, on top of a full 12-pillar × 7-economy submission.

### Statute re-fetch → coverage (2026-07-22 overnight)

The corpus-quality lever, executed. `refetch_statutes.py` routes each non-statute
corpus text through the economy's portal adapter (bpk/india_code/mekong) →
accepts only STATUTE-quality (Pasal-aware) text bigger than what's on disk.

**P6,7 batch: recovered ~21 primary statutes** (IND 5/8, THA 6/9, CHN 8/11,
MNG 1/2, RUS 1/2; IDN's remnants unrecoverable). Regenerating the 5 economies'
P6,7: official non-zero cells 22 → 24 (+2), and row counts up materially
(THA 27→40, CHN 44→51). Modest cell gain because P6/7 (our specialty) was
already near-max; the win there is denser evidence per cell.

**All-pillar batch running** (183 non-statute targets; IDN 48 / IND 42 / THA 27
/ RUS 25 the biggest) — the breadth pillars P1-5/8-12 have the real coverage
headroom (lower base + more summary/stub texts). Full-submission regen + new
coverage % to follow.

Also fixed the macOS "Python quit unexpectedly" crashes: the Playwright driver
segfaulted under load, and browser_mode="http" silently degraded to "auto"
(re-entering Playwright). Added a genuine HTTP-only BrowserMode that fails fast
after the curl_cffi/HTTP rungs — the batch tools now never launch a browser.

### coverage_report tool (built test-first) + the re-fetch's gap shift (2026-07-22)

Built `tools/coverage_report.py` test-first (vendored Matt Pocock `tdd` skill —
red-green, vertical slices; 7 tests): official_cell_coverage / by_economy /
by_pillar / uncovered_cells / coverage_delta / classify_gap / summarize_gaps,
plus a `--gaps` CLI. Validated: round2_final = 132/229 (57.6%), matching the
hand count; weak pillars surfaced (P1 0/3, P11 3/13, P5 8/26; strong P6 19/20).

**Dogfooding revealed the re-fetch worked:** the uncovered-cell root-cause split
on round2_final shifted from **26 extraction / 38 corpus-quality / 33 fetch**
(pre-refetch) to **49 extraction / 18 corpus-quality / 30 fetch** (post). The 80
recovered statutes converted ~20 corpus-quality gaps into extraction gaps — the
statute is now present, so the remaining gap is extraction recall, not missing
text. The round2_final_v2 regen (84%-statute corpus) then turns the cells where
extraction succeeds into actual coverage; delta measured via coverage_delta.

### Corpus re-fetch payoff: coverage 57.6% → 60.3% (2026-07-23)

Regenerated the full 12-pillar × 7-economy submission on the re-fetched corpus
(statute share 58% → 84%; `outputs/round2_final_v2`, 755 rows). Measured with
the new `coverage_report` tool: official non-zero cell coverage **132/229 (57.6%)
→ 138/229 (60.3%), +6 cells**. Pillar gains land on the breadth pillars whose
corpus was fixed — P7 +2, P11 +2, P3/P4/P5 +1 (P8 -1 is LLM sampling noise).

Modest gain from 80 recovered statutes because (a) many cells had another
covering law already, and (b) the gap shifted to EXTRACTION: the statute is now
present but extraction recall doesn't always surface the provision (the --gaps
split moved to 49 extraction / 30 fetch / 18 corpus). Corpus quality is now
largely solved; the remaining lever is extraction/classification recall — a
human-set precision/recall effort, per the earlier note. round2_final_v2 is the
new best submission.

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

## 2026-07-23 — TUI polish pair: thinking animation (#372) + theme.toml (#373)

Two stn-cli features driven from Discord/Telegram (first day of the channel
workflow — requests arrived from the phone, progress streamed back as edits).

**Thinking effects (#372).** The RAG chat's pending state was a frozen
`[dim]thinking…[/]`. Now: braille spinner at 10fps + phase verbs that follow
the actual pipeline (thinking → retrieving → reranking → drafting, advancing
every 3s, holding on the last) + an elapsed tail after 3s. The formatter
(`thinking_meta`) is pure and unit-tested; the widget timer is a thin shell.
The subtle bug pre-empted: both chat workers are `exclusive=True`, so a new
question cancels the in-flight one mid-await — without a `finally` guard the
orphaned message's timer would animate forever, claiming work that isn't
happening. Cancellation now freezes the spinner.

**User theming (#373).** `~/.config/stn/theme.toml` (same home as
credentials.json, so the compose `stn-config` volume already carries it):
10 palette slots + `dark` + `transparent`, `[thinking]` spinner/phases,
`[chat]` markers, `[widgets]` opacity. Layering: code defaults < file <
`STN_THEME_*` env — Docker configures via environment, no bind mount.
`transparent = true` = `ansi_default` background + `App.ansi_color`, the
mechanism of Textual's builtin ansi themes; the terminal emulator's own
opacity/blur then shows through. All 8 hardcoded `#10B981` in tui.py were
deduped into theme references while at it.

**The catch worth remembering:** all 25 unit tests were green while the app
crashed on import against the real user file. Textual's `Color` parses
8-digit alpha hex (`#13201bCC`); Rich's `Color.parse` — used by inline markup
and `Style(bgcolor=…)` — rejects it, so `BlockBar` died the moment `surface`
carried alpha. Only smoke-loading the user's actual `theme.toml` surfaced it.
Fix: `.rich(key)` accessor strips the alpha byte for Rich contexts (Textual
keeps it); regression test pins the split. Second lesson from the same PR:
tui.py loads the theme at import time, which silently made the whole suite
environment-dependent (a developer's `~/.config/stn/theme.toml` would leak
into test runs) — `tests/conftest.py` now pins `STN_CONFIG` to a nonexistent
path before anything imports tui. Test with the artifact users actually
produce, and keep import-time config out of test reach.

## 2026-07-23 — FETCH_GAP attack: 9 cells resolved (manifest + direct fetches)

6 false-positive FETCH_GAP cells had text already on disk but filed under a
different law_name. Added manifest entries pointing to existing text. 3 genuinely
new laws fetched via HTTP (LAO Procurement + Standardization, IND Companies Act).
Remaining 21 FETCH_GAP: JS portals, dead links, 403s — infrastructure-blocked.

## 2026-07-31 — TOP 20! Live pitch prep begins

**We made the top 20.** Pitch slot: **Aug 3, 14:00–14:15 Bangkok (GMT+7)**, team
[63] Sentinel. Pitch rules: 8 min presentation + 7 min judge Q&A. Judges may ask
to **run the prototype live on a specific case**. No retry if it crashes. 50% of
final score from live pitch; results Aug 5.

### Current repo state (post-OpenCode sprint + merge)

- **Coverage: 163/229 (71.2%)** — union of all per-pillar re-runs in `outputs/`.
  This is verified (`coverage_report.py outputs/`) and the committed worklist
  has 66 remaining gaps (37 extraction + 15 corpus-quality + 14 fetch-gap).
  Per-economy: CHN 26/36, IND 24/36, IDN 36/47, LAO 18/27, MNG 17/21, RUS 20/34,
  THA 22/28.
- **Key improvements from the OpenCode sprint:** pipeline name-resolution fix
  (53 false-positive FETCH_GAP cells unlocked), incremental pillar re-runs via
  qwen2.5:14b with 32K context. Coverage climbed from ~96 cells (early July) →
  161 → 163.
- **Bottleneck:** qwen2.5:14b extraction quality is below DeepSeek. DeepSeek
  budget exhausted (300 RMB). Extraction recall is the largest remaining gap (37).
- **Suite:** 808 passed, green.
- **Judge repo:** origin/main @ 4f72cc4, synced with all teammate work (#366–#381).

### Pitch-prep workstreams (revised for 71.2%)

1. **Merge + push to judge repo** — pull teammate work, commit multi-language
   changes, green suite, push. Judges see a current, active repo.
2. **Live-demo hardening** — `--from-corpus` must run fast (<2 min) and
   survive edge cases (corrupt file, missing pillar, bad economy name).
   Prep a single "hero command" that produces visible output every time.
3. **Pitch deck + demo script** — 8 slides max, 1 min each. Hero numbers
   (71.2% coverage, 96.2% grounding, 29% blind-verify, $12.96/$0 cost,
   808 tests). A 2-minute live-demo walkthrough (run China P6, show CSV
   output, show the audit trail).
4. **Q&A dry-run** — anticipate judge questions (worst-case: "run India P3
   live"), pre-run those, note the output.
5. **Fallback plan** — if screen-share or live run fails, have the output
   CSV/JSON ready to post in Zoom chat (per pitch rule #10).

### Immediate next actions

- [x] Pull teammate work (origin/main) + push — DONE (4f72cc4)
- [x] Commit multi-language changes + push — DONE
- [ ] Update README pitch numbers (71.2% / 808 tests)
- [ ] Verify `--from-corpus` smoke-tests for at least 3 economies
- [ ] Merge all per-pillar CSVs into ONE clean submission artifact for judges
- [ ] Build pitch deck (8 slides, 1 min each)
- [ ] Dry-run "hero command" live demo
- [x] Telegram Dong with TL;DR — DONE

## 2026-07-31 — gap-classification fix: aggregate manifest per (economy, indicator), not law_name

The gap worklist misclassified cells because `_gap_cell_status` joined the
corpus manifest by EXACT law_name, but the inventory law_name is often a
';'-joined bundle or worded differently. A statute that IS present under a
different name (e.g. THA 12.7's Telecommunications Business Act, 66k chars,
160 article markers) was never seen → the cell was mislabeled CORPUS_QUALITY,
and 6 cells with present-but-unmatched text were mislabeled FETCH_GAP.

Fix (test-first): `aggregate_cell_status` + `_gap_cell_status` now aggregate
all manifest entries per (economy, indicator) via the manifest's own
indicator_id. +2 tests, full suite 810 green.

Resulting reclassification (66 cells, same total, accurate causes):
- FETCH_GAP 14 → 8 (6 were false "no text" — text existed, name mismatch)
- CORPUS_QUALITY 15 → 17 (incl. cells now correctly seen as having text)
- EXTRACTION 37 → 41 (THA 12.7 and others correctly re-tagged as statute-present)

So the real attack surface is even more extraction-leaning than the worklist
suggested, and 6 of the "blocked-portal" fetch gaps were never blocked.

## 2026-07-31 — FETCH_GAP honest-verdict: all 8 are hard blockers

Wayback Machine: no snapshot for any of the 8 FETCH_GAP URLs (checked via
archive.org/wayback/available). garant.ru 152-FZ/149-FZ: the stored text is a
title-only TOC page (Статья 18 = heading list, no body) — the real body is
JS-loaded and defeats the full fallback chain (curl_cffi → HTTP/PDF →
Playwright → OpenCLI → Wayback → Google Cache, all tried). nbtc.go.th
timeouts, chinafilm.gov.cn 404. So the 8 fetch gaps stay honest FETCH_GAP —
the reclassification earlier proved 6 of the original 14 were never blocked,
but these 8 genuinely are.

## 2026-08-01 — the human-feedback loop was never connected (three silent breaks)

Approve/reject in the Workbench was supposed to shape future extractions.
`providers.base._get_recent_corrections()` injects recent rejections into the
prompt as negative few-shot examples. It has never returned a single row.

Three independent breaks, each failing silently:
1. `api/review.py` inserted into `audit_trail` WITHOUT `reviewer_notes`, while
   the reader's WHERE required that column non-empty. `ReviewRequest.
   reviewer_notes` existed and was documented "for fine-tuning" — nothing wrote
   it, and no UI collects it.
2. Gating on a note keeps the loop dead regardless: a REJECTION is the signal,
   the note is colour. WHERE now selects every non-compliant mapping.
3. The reader hardcoded `host=postgres port=5432`, ignoring `DATABASE_URL`. The
   writer uses `auth._db_connect` (DATABASE_URL first), so from the host they
   addressed different databases and the reader could not resolve its hostname.

A bare `except: return ""` made all three look identical to "no rejections
yet". Failures now log a warning that says the loop is not contributing. The
"" fallback stays — a missing DB must never break extraction (judge CLI ships
no psycopg2). +10 tests.

## 2026-08-01 — RLVR: a broken verifier was being scored as a "no" (81.25% → 93.75%)

The `--with-llm` measurement gates whether best-of-N gets wired. Measured from
committed code at 708976b it read **81.25%**, stable over three runs — below
the harness's own ~90% bar. Every loss was a `page_dump` beating the real
provision. Three causes:

- **An errored verifier is not a verdict.** `EligibilityVerifier` swallows its
  own LLM/parse errors and abstains (right for the pipeline — precision-first).
  The reward read that as "ineligible" and scored 0.0, penalising whichever
  candidate hit the error. In `sgp-cpc-7-5-section-20` that alone lost it.
  `EligibilityResult.verifier_failed` now marks it; the reward drops the term
  from the DENOMINATOR (a neutral 1.0 would still move the weighted mean).
- **This falsified the harness's "failures are reported loudly" promise** — the
  inner handler meant the loud path counted zero. Now honest, and the first
  such run shows **7 of 69 eligibility calls failing with ExtractionError**
  (~10%), all previously scored as real negatives. The old 87.5% and the
  81.25% were both polluted by it.
- **Existence indicators must exempt eligibility under the LLM arm.** 7.1/7.2
  score an instrument's existence, so a bare title IS the answer.
  `single_provision` was already exempt; eligibility was kept because the
  deterministic branches apply no objectives-clause check. True of that arm,
  false of the LLM arm, which called the correct evidence "a statement of
  legislative purpose, not a provision-level measure"
  (`sgp-cybersecurity-7-2-framework`) and blessed the dump around it. **Fifth**
  instance of a provision-shape prior inverting on 7.1/7.2.

Also: `render_markdown` hardcoded "(no API calls, no network)" onto EVERY
report, so `--with-llm` runs claimed they had stayed offline while billing per
candidate. And the stale 87.5% baseline was stamped `fd0949b` — the commit
BEFORE the seam merged (#381), i.e. produced from an uncommitted working tree.
It was never reproducible from committed code.

Offline run unchanged at 100% / 0.9360; none of this touches the deterministic
path. Full suite 903 green.

**Open lead:** the eligibility call goes through `provider.query`, which uses
`temperature=0.3` and no `response_format=json_object` — unlike the structured
extraction path (`temperature=0`, JSON mode). That is the likely source of the
~10% `ExtractionError` parse failures, and it also means the gating measurement
is not reproducible by construction.
