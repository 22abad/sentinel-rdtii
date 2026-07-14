# Golden Set expansion — legal review record

The candidate set contains 29 cases across 10 documents. It covers every
Pillar 6/7 indicator with at least one positive and one boundary negative, and
covers both pillars for Australia, Malaysia, and Singapore.

All 29 cases and 10 documents are approved. The substantive lead completed the
expansion review on 2026-07-14 against RDTII 2.1; the machine-readable records
carry the same role, date, framework version, and approval status.

## Reviewed sources

The review covered official text/source status, provision number, scope,
indicator boundary, raw/category score, and rationale for each source:

| Document | Reviewed indicators | Decision |
| --- | --- | --- |
| Malaysia PDPA 2010, s.129 | 6.1–6.5, 7.1 | Approved |
| Singapore RDTII economy assessment | 6.3, 6.4, 6.5, 7.2 | Approved |
| Singapore PDPA 2012, s.11 | 7.1, 7.4, 7.5 | Approved |
| Singapore Cybersecurity Act 2018 | 7.1, 7.2, 7.4, 7.5 | Approved |
| Singapore Criminal Procedure Code 2010, s.20 | 7.2, 7.4, 7.5 | Approved |
| Australia Privacy Act 1988, APP 8.1 | 7.1 | Approved |

## Recorded approval procedure

1. Review every expansion case against the corresponding document record and
   official URL.
2. Correct the fixture text and its SHA-256 when a summary must be replaced by
   exact primary text.
3. Record `approved` with `reviewed_at`, reviewer role, RDTII 2.1, and review
   notes.
4. Record document approval after source text/version review.
5. Run `make golden-coverage`, the evaluation tests, and the offline evaluation.

`python scripts/check_golden_coverage.py --approved-only --json` verifies the
approved benchmark independently of any future pending additions.
