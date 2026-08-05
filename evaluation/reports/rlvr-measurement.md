# RLVR proxy-reward measurement

- Generated: `2026-07-31T23:22:39.379984+00:00`
- Commit: `708976b2356fba021b3514a58ef52f0beab67abd`
- Mode: `offline-synthetic-distractors` (no API calls, no network)
- Case-set SHA-256: `499cce05e40aed671202dd9be8189785d87a5700fdf5627e330e465a82d6fe25`
- Candidate sets: 16 (skipped 0), pairs compared: 69

## Headline

| Metric | Result |
| --- | ---: |
| Hygiene top-1 (proxy picks the real extraction) | 100.00% |
| Hygiene pairwise win rate | 100.00% |
| Full top-1 (incl. wrong-provision control) | 100.00% |
| Semantic pairwise win rate (control) | 100.00% |
| Mean proxy reward of the real extraction | 0.9360 |
| Mean oracle reward of the real extraction | 0.8500 |

The semantic row is a CONTROL, not a target. `neighbour_span` is a real,
correctly quoted provision from the same document that is simply the wrong
one. No label-free reward can rule it out; the number is reported so the
proxy's ceiling is visible rather than averaged away.

## Per distractor type

| Distractor | Class | Pairs | Reference wins | Win rate | Mean margin |
| --- | --- | ---: | ---: | ---: | ---: |
| `fragment` | hygiene | 16 | 16 | 100.00% | +0.1484 |
| `metadata_stripped` | hygiene | 16 | 16 | 100.00% | +0.2481 |
| `neighbour_span` | semantic | 7 | 7 | 100.00% | +0.0655 |
| `page_dump` | hygiene | 14 | 14 | 100.00% | +0.0790 |
| `paraphrase` | hygiene | 16 | 16 | 100.00% | +0.9360 |

## Reward configuration that produced these numbers

### Proxy component weights

| Component | Weight | Share of objective |
| --- | ---: | ---: |
| `citation_exactness` | 3.0 | 25.0% |
| `article_clause_specific` | 2.0 | 16.7% |
| `eligibility_supported` | 2.0 | 16.7% |
| `single_provision` | 1.5 | 12.5% |
| `not_truncated` | 1.5 | 12.5% |
| `metadata_complete` | 1.5 | 12.5% |
| `scope_resolved` | 0.5 | 4.2% |

### Hard gates (any failure collapses the total to 0)

`quote_present` `quote_grounded` `offsets_recover_quote` `score_in_allowed_tiers` `not_a_section_header` `quote_not_a_page_dump`

### Thresholds

| Constant | Value |
| --- | ---: |
| `quote_dump_gate_chars` | 2500 |
| `chunk_coverage_soft_limit` | 0.75 |
| `chunk_coverage_floor_value` | 0.4 |
| `chunker` | regex_legal_chunker (deterministic regex + UAX#29) |
| `existence_indicators` | 7.1, 7.2 |
| `existence_exempt_components` | single_provision, eligibility_supported (only when an external verdict is supplied — the deterministic branches are safe for a bare title, the LLM arm is not) |

### Oracle weights (labelled reward — never seen by the selector)

| Term | Value |
| --- | ---: |
| `evidence_threshold` | 0.8 |
| `w_matched` | 0.35 |
| `w_citation_exact` | 0.3 |
| `w_score_correct` | 0.15 |
| `w_article_correct` | 0.1 |
| `w_scope_correct` | 0.1 |
| `r_negative_case_hit` | -1.0 |
| `r_missed_positive` | -0.5 |
| `r_avoided_negative` | 0.25 |
| `score_term_active` | False |

_raw_score is not supplied in this study — it measures EVIDENCE selection, which is what best-of-N chooses between. Max achievable oracle total is therefore 0.85, not 1.0._

## Component discrimination (does each weighted term earn its weight?)

| Component | Weight | Mean on real | Mean on distractors | Discrimination |
| --- | ---: | ---: | ---: | ---: |
| `not_truncated` | 1.5 | 1.000 | 0.580 | +0.420 |
| `scope_resolved` | 0.5 | 1.000 | 0.768 | +0.232 |
| `single_provision` | 1.5 | 0.913 | 0.746 | +0.168 |
| `article_clause_specific` | 2.0 | 0.688 | 0.522 | +0.166 |
| `citation_exactness` | 3.0 | 1.000 | 0.844 | +0.156 |
| `metadata_complete` | 1.5 | 1.000 | 0.845 | +0.155 |
| `eligibility_supported` | 2.0 | 1.000 | 0.899 | +0.101 |

A component whose discrimination is ~0 is carrying weight in the objective
while contributing nothing to the decision. That is a candidate for removal,
not a neutral cost — every point of weight it holds is weight the terms that
do discriminate are not getting.

**Do not reweight straight off this column.** Several distractors were built
to break one specific component, so that component's discrimination partly
measures the distractor design rather than real model error — `scope_resolved`
and `metadata_complete` score well largely because `metadata_stripped` exists
to strip exactly those fields. The non-circular signal is a component that
separates across SEVERAL distractor kinds; use `by_kind_mean` in the JSON to
check that before moving any weight.


## Hygiene failures (the reward did not separate these)

None — the proxy outranked every hygiene distractor.

## How to read this

Hygiene top-1 is the number that gates wiring best-of-N. It says how often
the label-free reward would pick the real extraction out of a set that also
contains a fragment, a page-dump, a paraphrase, a heading and a
metadata-stripped variant. Below ~90% the reward is not safe to select on.

It does NOT say best-of-N will raise the benchmark. That needs real sampled
candidates from a live model, which costs API spend; this run is the
pre-flight that decides whether that spend is justified.
