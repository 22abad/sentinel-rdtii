# Judge-simulation test matrix

_Graded `main.py` runs from easy to hard, scored the way a judge grades output. Regenerate with `python tools/judge_test_matrix.py`._

## Tier 1 — Trivial (headline command)  (2/2 pass)

| Case | Result | Rows | Quality | Notes |
|---|---|---|---|---|
| SGP P6 offline (the headline command) | ✅ (85.3s) | 3 | verbatim 100% · url 100% · art 100% |  |
| SGP P7 offline | ✅ (48.0s) | 5 | verbatim 100% · url 100% · art 60% |  |

## Tier 2 — Mandatory scope + OCR  (3/3 pass)

| Case | Result | Rows | Quality | Notes |
|---|---|---|---|---|
| MYS P6+7 offline | ✅ (48.4s) | 2 | verbatim 100% · url 100% · art 100% |  |
| AUS P6+7 offline | ✅ (502.5s) | 38 | verbatim 100% · url 100% · art 95% |  |
| Scanned PDF -> citations (OCR) | ✅ (32.7s) | 7 | verbatim 100% · url 0% · art 86% |  |

## Tier 3 — Robustness / adversarial  (5/5 pass)

| Case | Result | Rows | Quality | Notes |
|---|---|---|---|---|
| Misspelled economy -> clean error | ✅ (0.1s) | 0 | — |  |
| Invalid pillar -> clean error | ✅ (0.0s) | 0 | — |  |
| Missing PDF path -> clean error | ✅ (0.3s) | 0 | — |  |
| Mixed-case economy tolerated | ✅ (95.2s) | 3 | verbatim 100% · url 100% · art 100% |  |
| Uncovered economy offline -> empty, honest | ✅ (0.2s) | 0 | — |  |

## Tier 4 — Live / network  (2/2 pass)

| Case | Result | Rows | Quality | Notes |
|---|---|---|---|---|
| SGP P6 seed-first (default, network) | ✅ (467.7s) | 28 | verbatim 100% · url 100% · art 100% |  |
| SGP P6 strict-live (auditable crawl) | ✅ (388.0s) | 25 | verbatim 100% · url 100% · art 100% |  |
