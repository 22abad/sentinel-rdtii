# Judge-simulation test matrix

_Graded `main.py` runs from easy to hard, scored the way a judge grades output. Regenerate with `python tools/judge_test_matrix.py`._

## Tier 1 — Trivial (headline command)  (2/2 pass)

| Case | Result | Rows | Quality | Notes |
|---|---|---|---|---|
| SGP P6 offline (the headline command) | ✅ (74.5s) | 3 | verbatim 100% · url 100% · art 100% |  |
| SGP P7 offline | ✅ (44.3s) | 5 | verbatim 100% · url 100% · art 60% |  |

## Tier 2 — Mandatory scope + OCR  (3/3 pass)

| Case | Result | Rows | Quality | Notes |
|---|---|---|---|---|
| MYS P6+7 offline | ✅ (37.2s) | 2 | verbatim 100% · url 100% · art 100% |  |
| AUS P6+7 offline | ✅ (531.1s) | 40 | verbatim 100% · url 100% · art 95% |  |
| Scanned PDF -> citations (OCR) | ✅ (32.8s) | 7 | verbatim 100% · url 0% · art 86% |  |

## Tier 3 — Robustness / adversarial  (5/5 pass)

| Case | Result | Rows | Quality | Notes |
|---|---|---|---|---|
| Misspelled economy -> clean error | ✅ (0.1s) | 0 | — |  |
| Invalid pillar -> clean error | ✅ (0.0s) | 0 | — |  |
| Missing PDF path -> clean error | ✅ (0.3s) | 0 | — |  |
| Mixed-case economy tolerated | ✅ (84.0s) | 3 | verbatim 100% · url 100% · art 100% |  |
| Uncovered economy offline -> empty, honest | ✅ (0.2s) | 0 | — |  |

## Tier 5 — Hard / honesty stress  (6/6 pass)

| Case | Result | Rows | Quality | Notes |
|---|---|---|---|---|
| Indicator filter (--indicators 6.1) | ✅ (0.2s) | 0 | — |  |
| All 12 pillars on a mandatory economy | ✅ (138.8s) | 8 | verbatim 100% · url 100% · art 75% |  |
| Mismatched-pillar PDF -> honest, no hallucination | ✅ (38.8s) | 0 | — |  |
| Malformed PDF -> clean error | ✅ (0.3s) | 0 | — |  |
| Blank PDF -> empty, honest | ✅ (0.5s) | 0 | — |  |
| Huge --limit does not crash | ✅ (67.5s) | 3 | verbatim 100% · url 100% · art 100% |  |
