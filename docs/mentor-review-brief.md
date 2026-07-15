# Mentor Review Session — team brief & run-of-show

_Prepared for the on-campus review (Prof. Jiangyuan Fu, Prof. Joseph Timoney,
Prof. Qian Xiao, TAs, and the visiting trade-law professor from Portugal).
90 minutes of mentor time; our job is to extract maximum actionable feedback
before the July 20 submission. Print this; assign presenters at the top._

## Run of show (suggested, 30 min presentation + discussion)

| Min | Segment | Presenter | Material |
|---|---|---|---|
| 0–3 | Problem & architecture in one picture | Dong | deck outline §1–3 |
| 3–8 | **Live demo**: `python main.py --economy Singapore --pillar 6` + scanned-PDF run | Dong | terminal (offline mode as backup) |
| 8–12 | Round 1 status: golden set signed off, 5 NEW laws, 500+ tests | Abel | deck §4–5 |
| 12–18 | **The benchmark**: 500 rows vs official DB, 251 exact (50.2%) / 351 evidence-backed (70.2%), 7 languages | Dong | `round2-meeting-report.md` |
| 18–22 | Legal-in-the-loop: Katie's verification session + adjudication findings | Katie | her exported results |
| 22–25 | Engineering war stories (pick 2: reasoning-budget starvation, prefix-cap blindness) | Eric/Abel | engineering log §5–6 |
| 25–30 | Our questions to you (below) | all | — |

## The one-slide numbers (memorize)

- Round 1 mandatory: **done + legally signed off**; judge command runs in one line; $0.01–0.05 per economy-pillar.
- Beyond mandatory: **61/61 indicators executable; 500 official baseline rows
  benchmarked; 251 exact score matches (50.2%), 351 evidence-backed (70.2%),
  fully automated, across 7 languages (36–60% exact-match band, incl.
  Cyrillic Mongolian and Russian).**
- Every row: verbatim quote (char-verified), article ref, official URL, SHA-256 provenance.

## Latest hardening — talking points (all landed since the last brief; all tested, all golden-safe)

_Frame: "we didn't just build it, we tried to break it the way a judge would."_

- **We simulated the judge's *real* command** (`main.py --economy X --pillar 6,7`,
  default + live discovery — not our clean `--offline` path) and audited every row.
  It exposed that a naive run was **58% noise on Singapore** — clauses lifted from
  *trade agreements* (SAFTA, the AU–SG Digital Economy Agreement) and an IMDA
  *blog article*. We added golden-safe filters that drop out-of-scope sources,
  fragment quotes, foreign-jurisdiction mislabels (a Malaysia PDPA page the model
  tagged "Hong Kong PDPO"), and one-statute domination. Result: the judge's own
  command now yields clean domestic-law output — **SGP 26→8, MYS 30→9, AUS 19,
  zero noise** — verified against the 29-case golden set with **0 regressions**.
- **A committed, reproducible submission sample** lives in
  `docs/r1-submission-sample/` (SGP/MYS/AUS × P6/P7, frozen 13-field schema).
- **Genuine NEW evidence, independently verified** (the discovery differentiator):
  - 🇦🇺 *Identity Verification Services Act 2023* (P7-I5) and *Privacy Amendment
    (Public Health Contact Information) Act 2020* — confirmed in force via the
    Federal Register API; indicators re-checked against the actual provision (we
    **retracted** the model's over-tags rather than ship them).
  - 🇹🇭 two *PDPA exemption Royal Decrees* (2020/2023) — verbatim provisions pulled
    from the Office of the Council of State; existence corroborated by DLA Piper.
  - Full audit trail in `docs/new-law-candidates.md`.
- **Rigor discipline** (say this — mentors reward it): every filter is verified to
  drop **0 of 29 legally-approved golden cases**; each candidate is checked against
  an authoritative source before it is claimed; what can't be verified is flagged,
  not asserted. 500+ automated tests, green.

## Questions to ask each mentor (the real payload)

**Prof. Timoney (CS/architecture):**
1. For the 3 Aug live pitch, which failure mode would you stress-test first —
   live crawling, OCR, or provider outage? (We have offline fallback; is that
   convincing or does it look like dodging?)
2. Is a 50.2% fully-automated exact-match rate against official evaluators a
   number to LEAD with or to contextualize carefully?

**Prof. Qian Xiao (AI-assisted legal documents):**
1. Our residual error is criterion-tier judgement (restrictive vs
   empowering-only provisions). Any known techniques for legal-tier
   classification you'd point us to before the finale?
2. Does our "LLM extracts, deterministic code scores" split match how you'd
   audit an AI legal tool?

**Visiting trade-law professor (Portugal):**
1. Show 2–3 of Katie's Task B disagreement rows: "The official evaluator
   scored 0, our engine 1.0 — the law empowers the ministry but doesn't
   impose the measure. Which reading is right under RDTII?"
2. **Timor-Leste**: we scouted the Jornal da República (Portuguese) — as the
   double-point bonus economy, is its legal landscape thin enough to cover
   meaningfully in 3 days? Would you be willing to sanity-check a 10-row
   sample if we produce one?

**Prof. Fu:**
1. From the 45→20 cut: what typically kills teams at this stage — missing
   deliverables, unreproducible setup, or weak differentiation?

## Demo pre-flight (do before the session)

- [ ] `git pull`; `.env` has DEEPSEEK_API_KEY; ollama running as fallback
- [ ] Rehearse: `python main.py --economy Singapore --pillar 6 --offline` (fast, deterministic)
- [ ] Scanned-PDF command ready in shell history (India procurement order)
- [ ] Tabs open: `docs/r1-submission-sample/` (the clean output), `docs/new-law-candidates.md` (the discoveries), `docs/round2-meeting-report.md`
- [ ] Optional wow: `docs/judge-test-report.md` (the graded judge-simulation matrix)
- [ ] If campus wifi fails: everything above runs offline

## What NOT to claim

- Do not say "50.2% accuracy" bare — say "251 of 500 fully-automated scores match
  the official evaluators exactly; the tool is a draft-for-review system, and
  scoring stays with the human researcher per the official Zone 3 guidance."
- Do not claim RAG retrieval in the CLI — say the embedding store is live in
  the web app; CLI integration is a finale-stage upgrade.
- Exact matches include correct abstentions. For LAO, say "37/62 exact (60%),
  with evidence found for 31/62" rather than treating exact match as extraction
  accuracy.
