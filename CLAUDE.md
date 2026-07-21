# CLAUDE.md — project rules (MUST follow)

Team SENTINEL · UN ESCAP RDTII 2.1 hackathon. These OVERRIDE default behavior. Re-read them when a long session has drifted.

## Standing rules (non-negotiable)
1. **Official answer key is ground truth.** Scores/mappings/rules come from `requirements/Hackthon Knowledge Products/` — the Round-1/2 Database xlsx (methodology sheet = criteria + allowed scores; economy sheets = the answer key with Coverage annotations), the framework PDFs, the submission templates. **Trust the official answer key over any external research (Gemini has been wrong even while quoting official text).**
2. **When unsure, read `requirements/` FIRST.** Never guess, never punt an answerable question to Dong. (Cost us twice: CSV column casing, indicator 6.5 — both were answerable from the docs.)
3. **No scoring hallucination.** Every indicator score is a value the official methodology defines for THAT indicator — no fabricated tier. R1 P6/P7 = 0 / 0.5 / 1 only (0.25 belongs to 3.4; 0.75 to 1.4; neither is in R1).
4. **Verify before presenting.** Independently confirm a law/status/indicator/score exists before showing or claiming it.
5. **爬不动大声报告,绝不造假.** If a fetch/crawl fails, say so loudly; never fabricate text, a seed, or a verbatim.
6. **pytest green before `gh pr merge`.** Update exact-set/count tests in the SAME commit as a new law/seed. All work via PR + squash-merge.
7. **Record everything.** Problem→fix stories to `docs/round2-engineering-log.md` AND Dong's vault (`obsidian_vault_22abad/UN-Hackerathon/`). Personal/pitch material → vault only, never the repo.
8. **Proactively Telegram Dong** on decisions/intervention, major milestones, or unfixable errors. Creds: `$CLAUDE_JOB_DIR/tmp/tg.env` (never commit).

## What the Round 1 submission IS (do NOT mislabel a CSV folder as "the submission")
- The Round 1 submission is a **5-deliverable package**, and **judges RUN our tool** to generate output: ① functional prototype (repo) + Quick Start README (a reviewer runs it in <10 min — official `Round 1 Submission Templates/README_template.md`), ② **structured output the TOOL produces** on `python main.py --economy X --pillar 6,7` (per-economy 13-col CSV + JSON), ③ slides, ④ video ≤10 min, ⑤ live demo + interview.
- **Never hand-stitch a "final_submission" CSV folder and call it the submission.** The deliverable is the tool that produces clean output on a fresh run. A hand-curated folder is the FAIL anti-pattern (see [[reproducibility-architecture]]).

## Indicator meanings — the AUTHORITATIVE scheme (a template sheet is WRONG)
- ⚠️ `OUTPUT_TEMPLATE_31MAY.xlsx` has an **"Indicator Reference" sheet that is a misleading GDPR-style placeholder** (it says P6-I1=prohibition, P6-I2=adequacy, P6-I3=SCCs, P6-I4=consent…). **Do NOT trust it.** The authoritative meanings are the **Round 1 Database methodology / RDTII 2.1 framework**:
  - **6.1** Ban and local processing · **6.2** Local storage · **6.3** Infrastructure requirement · **6.4** CONDITIONAL cross-border transfer (comparable-protection/consent — conditional transfer is 6.4, NOT 6.1) · **6.5** non-regulatory (participation in binding data-flow agreements).
  - **7.1** framework existence · **7.2** dedicated cybersecurity framework · **7.3** data retention (needs a SPECIFIC minimum period) · **7.4** DPO/accountability · **7.5** government access (court order → 0).
- The template's **column set (13 Title-Case columns) IS correct**; only its Indicator Reference sheet is wrong.

## Teacher-feedback quality bar (from the graded Assignment-2 files — what the grader rewards)
- **Off-topic / wrong-indicator law → remove** (grader on our own file: "Companies Act… more about storage/retention, remove"; "MAS Guidelines… not quite related, remove"). Our mapping gate (#285) enforces this.
- **Only enforced, binding law** — drop drafts, proposed, cancelled/repealed instruments.
- **Verbatim must literally state the mapped requirement** ("s125 did not mention the minimum 7 years"). A cite that doesn't contain the requirement is invalid.
- **7.3 = 0 unless a specific minimum retention period is stated** ("retain as long as necessary" / no period = 0).
- **One official, direct, working URL per row**; secondary/third-party links → Notes column. **Every row needs a timeframe** (Last Amended).
- **No invented score tiers** (no 0.75); score every measure. Coverage = horizontal when the law applies economy-wide.

## Key project facts (that are easy to forget)
- **Round 1 submits EVIDENCE ROWS, not scores.** The 13-column CSV (law → indicator → verbatim). Judges compute scores. Our internal deterministic scores are NOT submitted.
- **Submission CSV header = official Title Case** (`Economy, Law Name, ...`) per `OUTPUT_TEMPLATE_31MAY.xlsx` ("must match exactly"), plain UTF-8 no BOM. Internal field keys stay snake_case (`CSV_COLUMNS`); `CSV_HEADERS` is what's written.
- **Round 1 scope** = P6 (6.1-6.4) + P7 (7.1-7.5) × SGP/MYS/AUS. P6 has **no 6.5 as a regulatory indicator** — 6.5 + {1.1,1.2,1.3,2.4,4.4,4.7,4.8,5.6,9.2,12.10-13} are **non-regulatory** (external-data/treaty checks), not scored from a law.
- **Coverage = 27/27** official economy×indicator cells have a curated seed hinted for them (library = `data/law_library/manifest.jsonl`, **36 entries** — incl. MYS 6.2 ITA s82 + Service Tax s24, and MYS 7.5 Cyber Security Act 2024 s46 added 2026-07-21 after the Round-1 --offline run showed that cell empty). Seed-first + hint top-up guarantee each seed maps to its hinted indicator.
- **Government-data exclusion** applies ONLY to 6.1-6.4 + 7.3 (not blanket). **7.5** scores 1 only for access WITHOUT a court order (a warrant/magistrate order → 0). **6.1/6.2** score 1 only for HORIZONTAL scope; a sector-specific personal measure = 0.5.
- **Run:** `python main.py --economy X --pillar 6,7`. Providers: DeepSeek (`deepseek-v4-flash`, needs key in `.env`) for speed; Ollama (key-free) is the judge default. Search: free DuckDuckGo default, SerpApi if key present.
- **Deadlines:** demo recording + submission are imminent (mid-July 2026) — prioritize submission-ready output.

Detailed context lives in `docs/round2-engineering-log.md` and the vault. When context is lost mid-session, re-read those.
