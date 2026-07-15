# Judge-simulation test matrix

_Graded `main.py` runs from easy to hard, scored the way a judge grades output. Regenerate with `python tools/judge_test_matrix.py`._

## Tier 1 — Trivial (headline command)  (2/2 pass)

| Case | Result | Rows | Quality | Notes |
|---|---|---|---|---|
| SGP P6 offline (the headline command) | ✅ (84.8s) | 3 | verbatim 100% · url 100% · art 100% |  |
| SGP P7 offline | ✅ (48.8s) | 5 | verbatim 100% · url 100% · art 60% |  |

## Tier 2 — Mandatory scope + OCR  (3/3 pass)

| Case | Result | Rows | Quality | Notes |
|---|---|---|---|---|
| MYS P6+7 offline | ✅ (50.5s) | 2 | verbatim 100% · url 100% · art 100% |  |
| AUS P6+7 offline | ✅ (482.9s) | 38 | verbatim 100% · url 100% · art 95% |  |
| Scanned PDF -> citations (OCR) | ✅ (39.1s) | 8 | verbatim 100% · url 0% · art 88% |  |

## Tier 3 — Robustness / adversarial  (5/5 pass)

| Case | Result | Rows | Quality | Notes |
|---|---|---|---|---|
| Misspelled economy -> clean error | ✅ (0.1s) | 0 | — |  |
| Invalid pillar -> clean error | ✅ (0.0s) | 0 | — |  |
| Missing PDF path -> clean error | ✅ (0.4s) | 0 | — |  |
| Mixed-case economy tolerated | ✅ (72.1s) | 3 | verbatim 100% · url 100% · art 100% |  |
| Uncovered economy offline -> empty, honest | ✅ (0.3s) | 0 | — |  |

## Tier 5 — Hard / honesty stress  (6/6 pass)

| Case | Result | Rows | Quality | Notes |
|---|---|---|---|---|
| Indicator filter (--indicators 6.1) | ✅ (0.3s) | 0 | — |  |
| All 12 pillars on a mandatory economy | ✅ (134.3s) | 8 | verbatim 100% · url 100% · art 75% |  |
| Mismatched-pillar PDF -> honest, no hallucination | ✅ (32.4s) | 0 | — |  |
| Malformed PDF -> clean error | ✅ (0.4s) | 0 | — |  |
| Blank PDF -> empty, honest | ✅ (0.7s) | 0 | — |  |
| Huge --limit does not crash | ✅ (61.3s) | 3 | verbatim 100% · url 100% · art 100% |  |

## Tier 6 — Malformed-argument edge cases  (3/3 pass)

| Case | Result | Rows | Quality | Notes |
|---|---|---|---|---|
| Duplicate pillars 6,6,7 -> deduped | ✅ (143.2s) | 8 | verbatim 100% · url 100% · art 75% |  |
| Text file renamed .pdf -> clean error | ✅ (0.7s) | 0 | — |  |
| Zero pillar -> clean error | ✅ (0.1s) | 0 | — |  |
