# Legal-review priorities for the legal reviewer — indicator confirmation

_The discovery engine finds and verbatim-verifies NEW laws; the **indicator**
each provision maps to is confirmed by a legal reviewer. This is the list that
needs the reviewer's call before Round 1 submission. Every law below is genuine,
in-force, and verbatim-verified at an official source — only the RDTII indicator
assignment is open._

## Priority A — indicator diverges from the automated pipeline (6 laws)

These were caught by the 2026-07-17 extraction-reproducibility audit: the
content-extraction pipeline does not reproduce our analyst-assigned indicator, so
a human legal call decides the correct RDTII indicator.

| Law (economy) | Provision | Our analyst hint | Pipeline extracts | the reviewer's call |
|---|---|---|---|---|
| **Cyber Security Act 2024 (AUS)** | s3 objects; s27 ransomware reporting | 7.2 (dedicated cyber framework) | **11.1 (Standards)** | 7.2 vs 11.1 vs both? |
| **Digital ID Act 2024 (AUS)** | s48 biometric restrictions | 7.1 | empty / 7.4 (fuller) | 7.1 vs 7.4? |
| **Archives Act 1983 (AUS)** | record retention | 7.3 (retention) | **6.1 (storage)** | 7.3 vs 6.1? |
| **Crimes Act 1914 s3LA (AUS)** | computer-access assistance orders | 7.5 (lawful access) | empty | confirm 7.5? |
| **MAS Notice 658 (SGP)** | offshore outsourcing conditions | 6.4 (cross-border) | empty | confirm 6.4? |
| **Credit Reporting Agencies Act 2010 (MYS)** | security of credit information | 7.1 | empty | 7.1 vs 7.2/7.3? |

**Reassurance:** none of the RDTII heatmap cells depends *solely* on one of
these — each cell they touch is also covered by an auto-reproducing law
(SGP 6.4 ← PDP Regs 2021; MYS 7.1 ← A1727; AUS 7.1 ← NSW PPIP; AUS 7.3 ← IVS
Act; AUS 7.5 ← Surveillance Devices Act). So a "reject" on any of these does not
open a coverage gap — it just removes a supplementary row.

## Priority B — routine indicator confirmation (the other 15 NEW laws)

The 15 laws that auto-reproduce their indicator still want a legal sign-off on
the exact indicator (the engine over-tags — it maps one provision to several
indicators). These are in the review console
(the unified scoring console (`outputs/legal-review/rdtii-scoring-console.html`), 18 P6/7 cards) plus the
P12 CP(ETT) Regs 2024. Standard "confirm which indicator(s) the text genuinely
supports" review.

## Known open legal questions (from the mentor brief)

- Sub-national laws (VIC/NT/NSW/TAS/WA + this list's AUS state items) in a
  national index — do they score, and at what weight?
- The DPO provisions (MYS PDPA 2024 s12A) — 7.4 confirmed; any others?
- WA IPP 9 commenced **1 Jul 2026** — 16 days before submission. Confirm the team
  is comfortable citing a freshly-commenced provision.

_See `docs/r1-discovery-coverage.md` for the full heatmap and the reproducibility
audit, and `docs/new-law-candidates.md` for the discovery audit trail._
