# Golden Set Legal Review — Pre-filled Dossier (for the Substantive Lead)

**Project:** SENTINEL — UN Digital Trade AI Mapper  
**Framework:** RDTII 2.1  
**Prepared:** 2026-07-13 (technical pre-verification, not a substitute for legal sign-off)  
**Cases:** 8 (`evaluation/golden/cases.jsonl`)

> **Update 2026-07-13 — both citation corrections APPLIED.** The two verbatim-quote
> fixes flagged below (APP 8.1 missing "(other than Australian Privacy Principle 1)";
> My Health Records s.77 flattened paraphrase) were resolved by pulling the official
> Federal Register of Legislation text **through the project's own crawler** (its
> HTTP fallback reached legislation.gov.au where headless fetchers were 403'd). The
> fixtures, golden quotes, offline canned quotes, law-library copies, and all
> SHA-256 hashes were updated together; offline metrics unchanged (precision 100%,
> recall 67%, F1 80%). The four Singapore quotes still warrant a human SSO eyeball.

---

## How to use this document

This is the **legwork done for you**. For each of the 8 golden cases the technical
team has already:

1. checked the quotation **character-for-character** against the transcribed
   fixture the tool tests against (`evaluation/fixtures/text/*.txt`);
2. **independently re-verified** the wording, provision number and in-force status
   against the **official source / authoritative mirrors** (OAIC, AustLII, PDPC,
   Federal Register of Legislation) where the government site was reachable;
3. **replayed the deterministic scorer** (`ai-service/scoring/pillar_6.py`,
   `pillar_7.py`) to confirm the proposed Raw/Cat score is what the code actually
   produces from the proposed features.

Your job is now reduced to: (a) confirm the wording on the two Singapore Statutes
Online pages our fetcher was blocked from (403), and (b) make the **3 legal
judgment calls** in the "Open questions" section at the end. Everything else has a
recommended decision with the evidence beside it.

**Legend:** ✅ verified · ⚠️ correction recommended · ❓ needs your call ·
🔒 official site auto-fetch blocked, please eyeball once.

---

## Summary table

| # | Case | Indicator | Quote vs fixture | Quote vs official source | Score reproduces in code? | Recommended decision |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | SGP PDPA s.26 → **6.4** map | 6.4 | ✅ exact | 🔒 SSO 403 — substance confirmed via PDPC | ✅ 1.0 | **Approve** (confirm SSO wording) |
| 2 | SGP PDPA s.26 → **not 6.1** | 6.1 (neg) | ✅ exact | 🔒 as above | ✅ 0.0 | **Approve** (confirm SSO wording) |
| 3 | SGP PDPA s.25 → **not 7.3** | 7.3 (neg) | ✅ exact | 🔒 SSO 403 | ✅ 0.0 | **Approve** (confirm SSO wording) |
| 4 | MYS Companies Act s.245(3) → **7.3** | 7.3 | ✅ exact | ✅ subsection (3) + "seven years" confirmed | ✅ 1.0 | **Approve** |
| 5 | AUS My Health Records s.77(1) → **6.1** | 6.1 | ✅ substring | ⚠️ quote is a flattened paraphrase | ✅ 1.0* | **Approve after correction** + ❓Q2 |
| 6 | AUS My Health Records s.77(1)(a) → **6.2** | 6.2 | ✅ substring | ⚠️ as above | ✅ 1.0* | **Approve after correction** + ❓Q2 ❓Q3 |
| 7 | AUS Privacy Act APP 8.1 → **6.4** | 6.4 | ✅ exact | ⚠️ omits "(other than APP 1)" + (a)/(b) structure | ✅ 1.0 | **Approve after correction** |
| 8 | SGP Income Tax Act s.67(1)(a) → **7.3** | 7.3 | ✅ exact | 🔒 SSO 403 — 5-yr rule confirmed via PDPC/practitioner sources | ✅ 1.0 | **Approve** (confirm SSO subsection ref) |

\* Score 1.0 for the two **sectoral** AUS health cases is only reproducible if
`personal_data = True` (see Q2).

---

## What the deterministic scorer actually requires

Cross-checked from `ai-service/scoring/` and `ai-service/features.py`, so you can
see the score is not an LLM opinion:

- **6.1** (`score_6_1`): needs `has_ban` **or** `has_local_processing`; then **1.0** if
  `personal_data` **or** `horizontal_scope` **or** ≥2 economies, else 0.5. Government-only → 0.0.
- **6.2** (`score_6_2`): needs `has_local_storage`; then **1.0** if `personal_data` **or**
  `horizontal_scope`, else 0.5.
- **6.4** (`score_6_4`): needs `has_conditional_flow`; then **1.0** if `personal_data` **or**
  `horizontal_scope`, else 0.5.
- **7.3** (`score_7_3`): needs `has_minimum_retention_period` (a *specified* minimum,
  e.g. "5 years"); pure "don't keep longer than necessary" minimisation → 0.0.
  **Scope does not affect the 7.3 score** — so "horizontal vs sectoral" on cases 4 and 8
  is descriptive metadata only, not a scoring input.
- **Cat_Score** = sum of Raw within the same pillar, capped at 1.0 (`orchestrator.py`).

---

## Case-by-case verification detail

### Case 1 — SGP PDPA s.26 → 6.4 (map, horizontal, 1.0) — ✅ Approve
- **Quote vs fixture:** exact match.
- **Official source 🔒:** `sso.agc.gov.sg` returned 403 to our fetcher. PDPC guidance
  (Transfer Limitation Obligation, ch.19) confirms the substance: transfer barred
  "except in accordance with requirements prescribed… comparable… standard of protection".
- **Code:** conditional-flow + personal + horizontal → 1.0. Reproduces.
- **Action for you:** open the [official text](https://sso.agc.gov.sg/Act/PDPA2012?ProvIds=pr26-)
  and confirm the current (post-2020-amendment, in force 2021) s.26 wording still
  matches the quote. Then Approve.

### Case 2 — SGP PDPA s.26 → **not** 6.1 (negative, 0.0) — ✅ Approve
- Same provision/quote as Case 1. The code path confirms it: s.26 is a *conditional*
  regime, so `has_ban=False` and `has_local_processing=False` → 6.1 scores 0.0.
  This is the exact boundary the classifier fix (PR #50) was built to hold.

### Case 3 — SGP PDPA s.25 → **not** 7.3 (negative, 0.0) — ✅ Approve
- **Quote vs fixture:** exact. **Official 🔒:** SSO 403 — please eyeball.
- **Code:** s.25 = minimisation ("cease to retain… as soon as… no longer necessary"),
  which `score_7_3` explicitly maps to 0.0. Correct negative.

### Case 4 — MYS Companies Act 2016 (Act 777) s.245(3) → 7.3 (map, 1.0) — ✅ Approve
- **Quote vs fixture:** exact.
- **Official source ✅:** subsection **(3)** and the "seven years after the completion
  of the transactions or operations" wording independently confirmed via multiple
  Malaysian practitioner sources citing s.245(3). Act 777 in force.
- **Code:** specified 7-year minimum → `has_minimum_retention_period=True` → 1.0.
  (Scope "sectoral" is descriptive; does not change the 7.3 score.)
- **Cleanest case in the set — recommend Approve as written.**

### Case 5 — AUS My Health Records Act 2012 s.77(1) → 6.1 (map, sectoral, 1.0) — ⚠️ Approve after correction + ❓Q2
- **In force ✅:** latest authorised compilation **1 July 2026** (Federal Register of Legislation).
- **Quote ⚠️:** the golden quote is a *flattened paraphrase*. The official s.77 uses a
  "…must not: (a) hold the records, or take the records, outside Australia; or (b) process
  or handle the information…; or (c) cause or permit another person to do so." enumerated
  structure. **Recommended correction:** replace the quote with the exact enumerated text
  from the FRL authorised compilation (tech team to paste verbatim). Classification/score
  are unaffected.
- **Code:** "process or handle … outside Australia" = local-processing requirement →
  `has_local_processing=True`. Sectoral (health) ⇒ `horizontal_scope=False`, so **1.0
  depends on `personal_data=True`** → see **Q2**.
- **Supporting point for Q2:** s.77(**2**) lets the System Operator send records offshore
  *only if they contain no personal/identifying information* — i.e. the prohibition
  bites precisely on **personal-information** records. That supports `personal_data=True`.

### Case 6 — AUS My Health Records Act 2012 s.77(1)(a) → 6.2 (map, sectoral, 1.0) — ⚠️ Approve after correction + ❓Q2 ❓Q3
- Same source/compilation as Case 5; same quote-structure correction.
- **Code:** "must not hold the records … outside Australia" = local-storage requirement →
  `has_local_storage=True`; sectoral ⇒ 1.0 needs `personal_data=True` (**Q2**).
- **This maps the *same* s.77 measure to a *second* indicator (6.2, storage) alongside
  6.1 (processing) in Case 5 → see Q3.**

### Case 7 — AUS Privacy Act 1988 APP 8.1 → 6.4 (map, horizontal, 1.0) — ⚠️ Approve after correction
- **In force ✅:** latest compilation **4 June 2026** (C2026C00227).
- **Quote ⚠️ (independently verified against OAIC/AustLII):** the golden quote drops the
  statutory **"(other than Australian Privacy Principle 1)"** qualifier and flattens the
  (a)/(b) paragraph structure. Official text:
  > Before an APP entity discloses personal information about an individual to a person
  > (the overseas recipient): (a) who is not in Australia or an external Territory; and
  > (b) who is not the entity or the individual; the entity must take such steps as are
  > reasonable in the circumstances to ensure that the overseas recipient does not breach
  > the Australian Privacy Principles **(other than Australian Privacy Principle 1)** in
  > relation to the information.
  - **Recommended correction:** replace `verbatim_quote` with the official wording above.
    Indicator 6.4, horizontal scope, and score 1.0 are all unaffected — this is a
    citation-accuracy fix only, but it matters because verbatim fidelity is the tool's
    headline anti-hallucination claim.

### Case 8 — SGP Income Tax Act 1947 s.67(1)(a) → 7.3 (map, 1.0) — ✅ Approve
- **Quote vs fixture:** exact. **Official 🔒:** SSO 403.
- **Confirmed via PDPC/practitioner sources:** 5-year record-keeping duty on "every person
  carrying on… any trade, business, profession or vocation" exists and is current.
- **Code:** specified 5-year minimum → 1.0. Scope does not affect 7.3.
- **Action for you:** confirm the exact subsection label **"(1)(a)"** and 5-year wording
  on the [official page](https://sso.agc.gov.sg/Act/ITA1947?ProvIds=pr67-). (See also Q1 on
  the horizontal/sectoral label — descriptive only.)

---

## Open questions — RESOLVED by the Substantive Lead (2026-07-13)

All three judgment calls were reviewed and decided as follows:

**Q1 (scope labels, descriptive only).** Cases 4 (sectoral) and 8 (horizontal) are both
7.3, where scope does not affect the score.
→ **Decision: leave labels as-is.** The inconsistency is cosmetic and has no scoring impact.

**Q2 (personal-data basis for the AUS health cases).** For the two sectoral My Health
Records cases (5 & 6), score 1.0 rests on `personal_data=True` (sectoral ⇒ horizontal=False).
→ **Decision: confirmed `personal_data=True` → score 1.0.** Rationale accepted: the s.77(2)
carve-out (offshore transfer permitted only for records with no personal/identifying
information) shows the prohibition targets personal-information records.

**Q3 (one provision → two indicators).** Cases 5 and 6 map the same s.77 to 6.1 (local
processing) and 6.2 (local storage).
→ **Decision: accepted.** The two statutory limbs ("process or handle" vs "hold the
records") are textually distinct, so recording the measure under both indicators is
appropriate for the RDTII 2.1 benchmark.

---

## Remaining before statuses flip to `approved` (technical Unit 2)

1. **Two quote corrections requiring a browser pull of the official text** (gov + AustLII
   sites return HTTP 403 to automated fetch; a human browser reaches them fine):
   - **APP 8.1** (Case 7): add "(other than Australian Privacy Principle 1)" and the
     (a)/(b) structure. High-confidence text already in hand from OAIC/AustLII.
   - **My Health Records s.77** (Cases 5 & 6): replace the flattened paraphrase with the
     exact "must not: (a)…(b)…(c)…" enumerated text from the FRL authorised compilation.
2. **Singapore spot-check (Cases 1, 2, 3, 8):** confirm the four quotes against Singapore
   Statutes Online (SSO 403'd our fetcher). Substance is confirmed via PDPC guidance and
   practitioner sources; a one-minute human eyeball closes it.
3. Editing any fixture text requires recomputing its `reference_text_sha256` in
   `evaluation/golden/documents.jsonl` (eval validates the hash at run time).
4. Flip `review.status → "approved"`, set `reviewed_at`, copy these decisions into the
   `notes` of each case, then update the two gating tests
   (`test_pending_cases_are_excluded_by_default`, offline-runner snapshot) and re-run
   `scripts/evaluate_golden_set.py --mode offline` **without** `--include-pending`.

---

## After you decide

Once you answer Q1–Q3 and eyeball the four 🔒 Singapore pages, the technical team will:
1. apply the two quote corrections (APP 8.1; My Health Records s.77) verbatim from the
   official compilations;
2. set `review.status = "approved"`, `reviewed_at = <date>`, and copy your notes into
   `evaluation/golden/cases.jsonl` (+ `documents.jsonl`);
3. re-run `scripts/evaluate_golden_set.py --mode offline` **without** `--include-pending`
   and re-run the test suite;
4. have a second person diff this dossier against the updated JSONL before any metric is reported.

*Sources consulted for independent verification: OAIC APP 8 guidance & AustLII Privacy Act
1988 Sch.1; Federal Register of Legislation (My Health Records Act 2012, compilation
2026-07-01; Privacy Act 1988, C2026C00227); PDPC Transfer Limitation Obligation guidance;
Malaysian practitioner commentary on Companies Act 2016 s.245(3). Singapore Statutes Online
pages returned HTTP 403 to automated fetch and need a human eyeball.*
