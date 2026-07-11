# Golden Set Legal Review Form / 黄金集法律审核表

**Project:** SENTINEL — UN Digital Trade AI Mapper  
**Framework:** RDTII 2.1  
**Cases for review:** 8  
**Purpose:** Confirm the human ground truth used to calculate the tool's formal accuracy metrics.

---

## 1. Instructions for the Substantive Lead / 法律负责人须知

These eight records are proposed benchmark answers, not AI outputs for publication. They will be treated as the “answer key” when measuring mapping precision, recall, citation accuracy, scope accuracy, and scoring accuracy.

Please review each case against:

1. the current official legal text;
2. the RDTII 2.1 Guide and workshop guidance;
3. the indicator boundary and scoring criteria.

For every case, please check:

- whether the law is currently in force and the cited version is current;
- whether the title, year, law number and official URL are correct;
- whether the quotation is verbatim and the provision number is correct;
- whether the provision should or should not map to the proposed indicator;
- whether the scope is horizontal or sectoral;
- whether the proposed Raw Score and Cat Score are correct;
- whether the legal rationale accurately explains the result.

Choose one decision:

- **Approved as written** — every material field is correct;
- **Approved after correction** — the case is usable after the listed corrections;
- **Rejected** — the case should not be part of the Golden Set.

Please do **not** edit the project JSON files. Complete this Markdown form and return it to the technical team. The technical team will update the machine-readable records after review.

---

## 2. Reviewer details / 审核人信息

- Reviewer name:
- Role/title:
- Review date (`YYYY-MM-DD`):
- RDTII framework/version consulted:
- General comments:

---

## 3. Review summary / 审核汇总

| # | Case ID | Proposed result | Decision | Correction required? |
| ---: | --- | --- | --- | --- |
| 1 | `sgp-pdpa-6-4-section-26` | Map to 6.4; Raw Score 1 |  |  |
| 2 | `sgp-pdpa-6-1-section-26-negative` | Must not map to 6.1 |  |  |
| 3 | `sgp-pdpa-7-3-section-25-negative` | Must not map to 7.3 |  |  |
| 4 | `mys-companies-7-3-section-245` | Map to 7.3; Raw Score 1 |  |  |
| 5 | `aus-my-health-records-6-1-section-77` | Map to 6.1; Raw Score 1 |  |  |
| 6 | `aus-my-health-records-6-2-section-77` | Map to 6.2; Raw Score 1 |  |  |
| 7 | `aus-privacy-act-6-4-app-8-1` | Map to 6.4; Raw Score 1 |  |  |
| 8 | `sgp-income-tax-7-3-section-67` | Map to 7.3; Raw Score 1 |  |  |

Use `Approved`, `Correct`, or `Reject` in the Decision column.

---

## 4. Case-by-case review / 逐案审核

### Case 1 — Singapore PDPA Section 26 → Indicator 6.4

**Case ID:** `sgp-pdpa-6-4-section-26`

- Country: Singapore
- Proposed law: Personal Data Protection Act 2012
- Official source: https://sso.agc.gov.sg/Act/PDPA2012
- Proposed legal status: In force
- Proposed provision: Section 26
- Proposed indicator: 6.4 — Conditional flow regimes
- Proposed result: Should map
- Proposed scope: Horizontal
- Coverage: Personal data transferred outside Singapore
- Proposed Raw Score: 1.0
- Proposed Cat Score: 1.0

**Proposed evidence**

> An organisation must not transfer any personal data to a country or territory outside Singapore except in accordance with requirements prescribed under this Act to ensure that organisations provide a standard of protection to personal data so transferred that is comparable to the protection under this Act.

**Proposed rationale**

The provision permits transfer subject to comparable-protection requirements, so it is a conditional flow regime rather than an outright transfer ban.

**Reviewer checklist**

- [ ] Current official legal text/version confirmed
- [ ] Law title and URL confirmed
- [ ] Provision number confirmed
- [ ] Quotation confirmed verbatim
- [ ] Indicator 6.4 confirmed
- [ ] Horizontal scope confirmed
- [ ] Raw Score 1.0 confirmed
- [ ] Cat Score 1.0 confirmed
- [ ] Rationale confirmed

**Decision**

- [ ] Approved as written
- [ ] Approved after correction
- [ ] Rejected

Corrections/reviewer notes:


### Case 2 — Singapore PDPA Section 26 must not map to Indicator 6.1

**Case ID:** `sgp-pdpa-6-1-section-26-negative`

- Country: Singapore
- Proposed law: Personal Data Protection Act 2012
- Official source: https://sso.agc.gov.sg/Act/PDPA2012
- Proposed legal status: In force
- Proposed provision: Section 26
- Proposed indicator tested: 6.1 — Ban and local processing requirements
- Proposed result: **Must not map**
- Proposed scope: Horizontal
- Coverage: Personal data transferred outside Singapore
- Proposed Raw Score: 0.0 for this negative case
- Proposed Cat Score: 0.0 for this negative case

**Proposed evidence**

> An organisation must not transfer any personal data to a country or territory outside Singapore except in accordance with requirements prescribed under this Act to ensure that organisations provide a standard of protection to personal data so transferred that is comparable to the protection under this Act.

**Proposed rationale**

The operative exception allows transfers that meet prescribed safeguards. It should not be coded as an outright ban or local-processing requirement.

**Reviewer checklist**

- [ ] Current official legal text/version confirmed
- [ ] Provision and quotation confirmed
- [ ] Provision permits transfer subject to safeguards
- [ ] Exclusion from Indicator 6.1 confirmed
- [ ] Indicator 6.4 is the more appropriate classification
- [ ] Negative-case score confirmed
- [ ] Rationale confirmed

**Decision**

- [ ] Approved as written
- [ ] Approved after correction
- [ ] Rejected

Corrections/reviewer notes:


### Case 3 — Singapore PDPA Section 25 must not map to Indicator 7.3

**Case ID:** `sgp-pdpa-7-3-section-25-negative`

- Country: Singapore
- Proposed law: Personal Data Protection Act 2012
- Official source: https://sso.agc.gov.sg/Act/PDPA2012
- Proposed legal status: In force
- Proposed provision: Section 25
- Proposed indicator tested: 7.3 — Minimum period of data retention requirements
- Proposed result: **Must not map**
- Proposed scope: Horizontal
- Coverage: Retention limitation for personal data
- Proposed Raw Score: 0.0 for this negative case
- Proposed Cat Score: 0.0 for this negative case

**Proposed evidence**

> An organisation must cease to retain its documents containing personal data, or remove the means by which the personal data can be associated with particular individuals, as soon as it is reasonable to assume that the purpose for which that personal data was collected is no longer being served by retention of the personal data and retention is no longer necessary for legal or business purposes.

**Proposed rationale**

This is a retention-limitation rule and does not mandate a specified minimum retention period under Indicator 7.3.

**Reviewer checklist**

- [ ] Current official legal text/version confirmed
- [ ] Provision and quotation confirmed
- [ ] This is a maximum/necessity-based retention limitation
- [ ] No specified minimum retention period is imposed
- [ ] Exclusion from Indicator 7.3 confirmed
- [ ] Negative-case score confirmed
- [ ] Rationale confirmed

**Decision**

- [ ] Approved as written
- [ ] Approved after correction
- [ ] Rejected

Corrections/reviewer notes:


### Case 4 — Malaysia Companies Act Section 245(3) → Indicator 7.3

**Case ID:** `mys-companies-7-3-section-245`

- Country: Malaysia
- Proposed law: Companies Act 2016 (Act 777)
- Official source: https://www.ssm.com.my/pages/legal_framework/document/act%20777%20reprint.pdf
- Proposed legal status: In force
- Proposed provision: Section 245(3)
- Proposed indicator: 7.3 — Minimum period of data retention requirements
- Proposed result: Should map
- Proposed scope: Sectoral
- Coverage: Company accounting records
- Proposed Raw Score: 1.0
- Proposed Cat Score: 1.0

**Proposed evidence**

> The company shall retain the records referred to in subsection (1) for seven years after the completion of the transactions or operations to which the entries relate.

**Proposed rationale**

The provision imposes a specified seven-year minimum retention period on company accounting records.

**Reviewer checklist**

- [ ] Current official legal text/version confirmed
- [ ] Act number, provision and quotation confirmed
- [ ] Seven-year minimum retention obligation confirmed
- [ ] Indicator 7.3 confirmed
- [ ] Sectoral/horizontal classification confirmed
- [ ] Raw Score 1.0 confirmed
- [ ] Cat Score 1.0 confirmed
- [ ] Rationale confirmed

**Decision**

- [ ] Approved as written
- [ ] Approved after correction
- [ ] Rejected

Corrections/reviewer notes:


### Case 5 — Australia My Health Records Act Section 77(1) → Indicator 6.1

**Case ID:** `aus-my-health-records-6-1-section-77`

- Country: Australia
- Proposed law: My Health Records Act 2012
- Official source: https://www.legislation.gov.au/C2012A00063/latest/text
- Proposed legal status: In force
- Proposed provision: Section 77(1)
- Proposed indicator: 6.1 — Ban and local processing requirements
- Proposed result: Should map
- Proposed scope: Sectoral
- Coverage: Records and information in the My Health Record system
- Proposed Raw Score: 1.0
- Proposed Cat Score: 1.0

**Proposed evidence**

> must not hold the records, or take the records, outside Australia; process or handle the information relating to the records outside Australia

**Proposed rationale**

The provision requires covered My Health Record participants to process or handle the relevant information within Australia.

**Reviewer checklist**

- [ ] Current authorised compilation confirmed
- [ ] Provision and quotation confirmed
- [ ] Local-processing requirement confirmed
- [ ] Commercial/non-government relevance confirmed
- [ ] Indicator 6.1 confirmed
- [ ] Sectoral scope confirmed
- [ ] Personal-data basis for Raw Score 1.0 confirmed
- [ ] Cat Score 1.0 confirmed
- [ ] Rationale confirmed

**Decision**

- [ ] Approved as written
- [ ] Approved after correction
- [ ] Rejected

Corrections/reviewer notes:


### Case 6 — Australia My Health Records Act Section 77(1)(a) → Indicator 6.2

**Case ID:** `aus-my-health-records-6-2-section-77`

- Country: Australia
- Proposed law: My Health Records Act 2012
- Official source: https://www.legislation.gov.au/C2012A00063/latest/text
- Proposed legal status: In force
- Proposed provision: Section 77(1)(a)
- Proposed indicator: 6.2 — Local storage requirements
- Proposed result: Should map
- Proposed scope: Sectoral
- Coverage: Records in the My Health Record system
- Proposed Raw Score: 1.0
- Proposed Cat Score: 1.0

**Proposed evidence**

> must not hold the records, or take the records, outside Australia

**Proposed rationale**

The provision requires covered My Health Record records to be held within Australia, constituting a local-storage requirement.

**Reviewer checklist**

- [ ] Current authorised compilation confirmed
- [ ] Provision and quotation confirmed
- [ ] Local-storage requirement confirmed
- [ ] Recording the same measure under both 6.1 and 6.2 is appropriate
- [ ] Sectoral scope confirmed
- [ ] Personal-data basis for Raw Score 1.0 confirmed
- [ ] Cat Score 1.0 confirmed
- [ ] Rationale confirmed

**Decision**

- [ ] Approved as written
- [ ] Approved after correction
- [ ] Rejected

Corrections/reviewer notes:


### Case 7 — Australia Privacy Act APP 8.1 → Indicator 6.4

**Case ID:** `aus-privacy-act-6-4-app-8-1`

- Country: Australia
- Proposed law: Privacy Act 1988
- Official source: https://www.legislation.gov.au/C2004A03712/latest/text
- Proposed legal status: In force
- Proposed provision: Australian Privacy Principle 8.1
- Proposed indicator: 6.4 — Conditional flow regimes
- Proposed result: Should map
- Proposed scope: Horizontal
- Coverage: Cross-border disclosure of personal information
- Proposed Raw Score: 1.0
- Proposed Cat Score: 1.0

**Proposed evidence**

> Before an APP entity discloses personal information about an individual to a person who is not in Australia or an external Territory and who is not the entity or the individual, the entity must take such steps as are reasonable in the circumstances to ensure that the overseas recipient does not breach the Australian Privacy Principles in relation to the information.

**Proposed rationale**

APP 8.1 permits overseas disclosure subject to reasonable steps ensuring equivalent compliance, which is a conditional-flow obligation.

**Reviewer checklist**

- [ ] Current authorised compilation confirmed
- [ ] APP number and quotation confirmed
- [ ] Conditional-flow obligation confirmed
- [ ] Indicator 6.4 confirmed
- [ ] Horizontal scope confirmed
- [ ] Raw Score 1.0 confirmed
- [ ] Cat Score 1.0 confirmed
- [ ] Rationale confirmed

**Decision**

- [ ] Approved as written
- [ ] Approved after correction
- [ ] Rejected

Corrections/reviewer notes:


### Case 8 — Singapore Income Tax Act Section 67(1)(a) → Indicator 7.3

**Case ID:** `sgp-income-tax-7-3-section-67`

- Country: Singapore
- Proposed law: Income Tax Act 1947
- Official source: https://sso.agc.gov.sg/Act/ITA1947?ProvIds=pr67-
- Proposed legal status: In force
- Proposed provision: Section 67(1)(a)
- Proposed indicator: 7.3 — Minimum period of data retention requirements
- Proposed result: Should map
- Proposed scope: Horizontal
- Coverage: Tax records for trades, businesses, professions and vocations
- Proposed Raw Score: 1.0
- Proposed Cat Score: 1.0

**Proposed evidence**

> Every person carrying on or exercising any trade, business, profession or vocation must keep and retain in safe custody sufficient records for a period of 5 years from the year of assessment to which any income relates to enable the person's income and allowable deductions under this Act to be readily ascertained by the Comptroller or any officer authorised in that behalf by the Comptroller.

**Proposed rationale**

The provision requires covered taxpayers to keep sufficient records for a specified five-year minimum period.

**Reviewer checklist**

- [ ] Current official legal text/version confirmed
- [ ] Provision and quotation confirmed
- [ ] Five-year minimum retention obligation confirmed
- [ ] Indicator 7.3 confirmed
- [ ] Horizontal/sectoral classification confirmed
- [ ] Raw Score 1.0 confirmed
- [ ] Cat Score 1.0 confirmed
- [ ] Rationale confirmed

**Decision**

- [ ] Approved as written
- [ ] Approved after correction
- [ ] Rejected

Corrections/reviewer notes:


---

## 5. Final reviewer declaration / 最终确认

I confirm that I reviewed the cases marked “Approved” against the cited official legal sources and the RDTII 2.1 methodology. Any required corrections are recorded in this form.

- Reviewer name:
- Signature or written confirmation:
- Date (`YYYY-MM-DD`):

---

## 6. Technical-team handoff / 技术团队后续操作

After receiving the completed form, the technical team must:

1. apply every correction to `evaluation/golden/cases.jsonl` and, where necessary, `evaluation/golden/documents.jsonl`;
2. set approved cases to `review.status = "approved"`;
3. record the actual review date in `review.reviewed_at`;
4. preserve reviewer notes in the machine-readable record;
5. validate hashes and schema;
6. run the formal evaluation without `--include-pending`;
7. have a second person compare this form with the updated JSONL before reporting metrics.

Example approved review block:

```json
"review": {
  "status": "approved",
  "reviewer_role": "Substantive Lead",
  "reviewed_at": "2026-07-12",
  "framework_version": "RDTII 2.1",
  "notes": "Approved against the current official legal text."
}
```
