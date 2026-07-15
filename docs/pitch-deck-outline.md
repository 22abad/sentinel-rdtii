# Technical Pitch Deck — content outline

_For the official template (`requirements/Hackthon Knowledge Products/Round 1
Submission Templates/Pitch Deck_REGTECH_rev1.pptx`). Also serves as the
Thursday (Jul 16) mentor-review walkthrough. Judges include non-technical
reviewers; each slide leads with the claim, not the mechanism. Every number
below traces to a JSON/markdown artifact in the repo._

## 1. Problem (1 slide)

~100 pages of unstructured, multilingual trade regulation per economy;
researchers hand-search portals, hand-extract provisions, hand-map to RDTII
indicators. Slow, unrepeatable, error-prone. (Rubric anchor: this is Zones
1+2, the judges' stated automation priorities.)

## 2. Solution in one picture (1 slide)

Pipeline diagram: discover (seed-first) → fetch/OCR → extract → verify
verbatim → deterministic score → 13-field CSV/JSON.
Tagline: **"The LLM never decides the score."**

## 3. Anti-hallucination architecture (1 slide) — the 40% accuracy story

- Every row carries a **verbatim quote verified character-for-character**;
  unverifiable mappings are rejected, not shown.
- Deterministic Python maps extracted criterion → published RDTII score,
  citing the official criteria text (auditable in seconds).
- SHA-256-verified law cache; NEW/KNOWN reconciled against the official
  ESCAP Legal Inventory (195 laws).

## 4. Round 1 mandatory scope — done and hardened (1 slide)

- P6/P7 × Singapore/Australia/Malaysia; golden set **legally signed off**.
- Seed-first retrieval: a judge's 10-minute run is never hostage to a live
  crawl (offline mode = same pipeline, zero network).
- 482-test suite; judge command: `python main.py --economy Singapore --pillar 6`.

## 5. Discovery of NEW evidence (1 slide) — the judges' differentiator

5 genuine NEW in-force laws found beyond the sample kit (e.g. Australia's
Identity Verification Services Act 2023), each cached with URL + SHA-256 +
human-review gate. The Queensland Information Privacy Act is treated as
baseline evidence and is not claimed as NEW.

## 6. Beyond mandatory: the full methodology, measured (1–2 slides) — the wow

- **All 61 RDTII indicators (12 pillars) executable**: specs + deterministic
  rules generated from the official methodology; adding an indicator is a
  data change.
- Benchmarked against the **official Round 2 database itself**:
  **464 rows · 78% evidence yield · 46% exact score agreement, fully
  automated** — consistent (41–57%) across **7 languages** incl. Thai,
  Mongolian (Cyrillic), Russian. Table per economy from
  `docs/round2-meeting-report.md`.
- Honest footnotes ready for Q&A: LAO composition (15 evidence-backed +
  18 correct abstentions), IDN dense-doc timeouts, corpus coverage by
  economy.

## 7. Technical resilience (1 slide) — the 30% resilience story

- Live portal crawling + Wayback fallback + browser path for JS portals
  (Mongolia's legalinfo.mn: 15% → **100% corpus coverage**).
- OCR on scanned PDFs with measured CER (`ocr_quality_cer` per row).
- Failure containment: one bad source never aborts a run; every failure
  recorded, never hidden.

## 8. Architecture & no vendor lock-in (1 slide) — the 30% architecture story

- Swap LLM by env var (`RDTII_LLM_PROVIDER`): DeepSeek / OpenAI / Gemini /
  Claude / **Ollama open-weight fallback (no API key)**; automatic failover
  provider as judge-safety net.
- Modular: crawler / OCR / extraction / scoring / submission are separable
  services; DB-free CLI for judges.
- Cost: DeepSeek flash ≈ $0.5–1 per full economy evaluation (measured).

## 9. What we learned (1 slide) — mentors love this; feeds the interview

Three engineering war stories with fixes shipped (from
`docs/round2-engineering-log.md`): reasoning-model budget starvation
(finish_reason=length diagnosis), prefix-cap blindness (P7 0/10 → 9/10),
no-timeout hangs. "Every failure mode found became a merged, tested fix."

## 10. Team & ask (1 slide)

Roles (tech lead / substantive lead / legal reviewer); roadmap to the
finale: close criterion-tier gap, Timor-Leste bonus, human-review workflow.

---

### Q&A appendix slides (have ready, don't present)

- Full per-pillar accuracy rollup table
- LAO/IDN caveat detail
- Cost breakdown per economy
- NEW-law dossiers (QLD act provenance chain)
