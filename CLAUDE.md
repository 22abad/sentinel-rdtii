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

## Key project facts (that are easy to forget)
- **Round 1 submits EVIDENCE ROWS, not scores.** The 13-column CSV (law → indicator → verbatim). Judges compute scores. Our internal deterministic scores are NOT submitted.
- **Submission CSV header = official Title Case** (`Economy, Law Name, ...`) per `OUTPUT_TEMPLATE_31MAY.xlsx` ("must match exactly"). Internal field keys stay snake_case (`CSV_COLUMNS`); `CSV_HEADERS` is what's written.
- **Round 1 scope** = P6 (6.1-6.4) + P7 (7.1-7.5) × SGP/MYS/AUS. P6 has **no 6.5 as a regulatory indicator** — 6.5 + {1.1,1.2,1.3,2.4,4.4,4.7,4.8,5.6,9.2,12.10-13} are **non-regulatory** (external-data/treaty checks), not scored from a law.
- **Coverage = 27/27** official economy×indicator cells have a curated seed hinted for them (library = `data/law_library/manifest.jsonl`, 33 entries). Seed-first + the #261 hint top-up guarantee each seed maps to its hinted indicator.
- **Government-data exclusion** applies ONLY to 6.1-6.4 + 7.3 (not blanket). **7.5** scores 1 only for access WITHOUT a court order (a warrant/magistrate order → 0). **6.1/6.2** score 1 only for HORIZONTAL scope; a sector-specific personal measure = 0.5.
- **Run:** `python main.py --economy X --pillar 6,7`. Providers: DeepSeek (`deepseek-v4-flash`, needs key in `.env`) for speed; Ollama (key-free) is the judge default. Search: free DuckDuckGo default, SerpApi if key present.
- **Deadlines:** demo recording + submission are imminent (mid-July 2026) — prioritize submission-ready output.

Detailed context lives in `docs/round2-engineering-log.md` and the vault. When context is lost mid-session, re-read those.
