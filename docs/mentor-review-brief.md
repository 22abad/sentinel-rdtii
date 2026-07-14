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
| 8–12 | Round 1 status: golden set signed off, 5 NEW laws, 482 tests | Abel | deck §4–5 |
| 12–18 | **The accuracy benchmark**: 464 rows vs official DB, 46% exact / 78% evidence, 7 languages | Dong | `round2-meeting-report.md` |
| 18–22 | Legal-in-the-loop: Katie's verification session + adjudication findings | Katie | her exported results |
| 22–25 | Engineering war stories (pick 2: reasoning-budget starvation, prefix-cap blindness) | Eric/Abel | engineering log §5–6 |
| 25–30 | Our questions to you (below) | all | — |

## The one-slide numbers (memorize)

- Round 1 mandatory: **done + legally signed off**; judge command runs in one line; $0.01–0.05 per economy-pillar.
- Beyond mandatory: **61/61 indicators executable; 464 official baseline rows
  benchmarked; 46% exact score agreement, 78% evidence yield, fully automated,
  across 7 languages (41–57% band, incl. Cyrillic Mongolian and Russian).**
- Every row: verbatim quote (char-verified), article ref, official URL, SHA-256 provenance.

## Questions to ask each mentor (the real payload)

**Prof. Timoney (CS/architecture):**
1. For the 3 Aug live pitch, which failure mode would you stress-test first —
   live crawling, OCR, or provider outage? (We have offline fallback; is that
   convincing or does it look like dodging?)
2. Is a 46% fully-automated exact-match rate against official evaluators a
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
- [ ] `docs/round2-meeting-report.md` + `review.html` open in tabs
- [ ] If campus wifi fails: everything above runs offline

## What NOT to claim

- Do not say "46% accuracy" bare — say "46% of fully-automated scores match
  the official evaluators exactly; the tool is a draft-for-review system, and
  scoring stays with the human researcher per the official Zone 3 guidance."
- Do not claim RAG retrieval in the CLI — say the embedding store is live in
  the web app; CLI integration is a finale-stage upgrade.
- LAO's 53% headline includes 18 correct abstentions — say "evidence-backed
  exact matches" if pressed (15/62 evidence-backed exact).
