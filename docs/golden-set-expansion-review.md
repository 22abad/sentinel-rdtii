# Golden Set expansion — legal review queue

The candidate set contains 29 cases across 10 documents. It covers every
Pillar 6/7 indicator with at least one positive and one boundary negative, and
covers both pillars for Australia, Malaysia, and Singapore.

This is a structural milestone, not a new accuracy claim. The original eight
cases remain the only approved labels. Every item below is `pending` and is
excluded from formal evaluation unless `--include-pending` is explicitly used.

## New source review

The substantive lead must confirm the current official text, provision number,
scope, indicator boundary, raw/category score, and rationale for each source:

| Document | Candidate indicators | Required decision |
| --- | --- | --- |
| Malaysia PDPA 2010, s.129 | 6.1–6.5, 7.1 | Confirm amended text and conditional-flow boundaries |
| Singapore RDTII economy assessment | 6.3, 6.4, 6.5, 7.2 | Confirm economy-wide absence/presence findings against current sources |
| Singapore PDPA 2012, s.11 | 7.1, 7.4, 7.5 | Confirm exact DPO wording and horizontal scope |
| Singapore Cybersecurity Act 2018 | 7.2, 7.4, 7.5 | Replace summary with exact provision and confirm framework scope |
| Singapore Criminal Procedure Code 2010, s.20 | 7.2, 7.4, 7.5 | Replace summary with exact text; analyse personal-data reach and judicial oversight |

The Australia Privacy Act 7.1 candidate also requires confirmation that the
framework is comprehensive for RDTII purposes despite statutory exemptions.

## Approval procedure

1. Review every case in `evaluation/golden/cases.jsonl` whose status is
   `pending` against the corresponding document record and official URL.
2. Correct the fixture text and its SHA-256 when a summary must be replaced by
   exact primary text.
3. Set a case to `approved` only with `reviewed_at`, reviewer role, RDTII 2.1,
   and a note recording the legal conclusion.
4. Approve a new document only after its source text/version is confirmed.
5. Run `make golden-coverage`, the evaluation tests, and the offline evaluation.

`python scripts/check_golden_coverage.py --approved-only --json` gives the
remaining formal-approval gaps without conflating pending candidates with the
approved benchmark.
