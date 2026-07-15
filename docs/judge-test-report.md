# Judge-simulation test matrix

_Graded `main.py` runs from easy to hard, scored the way a judge grades output. Regenerate with `python tools/judge_test_matrix.py`._

## Tier 5 — Hard / honesty stress  (6/6 pass)

| Case | Result | Rows | Quality | Notes |
|---|---|---|---|---|
| Indicator filter (--indicators 6.1) | ✅ (0.3s) | 0 | — |  |
| All 12 pillars on a mandatory economy | ✅ (114.8s) | 8 | verbatim 100% · url 100% · art 75% |  |
| Mismatched-pillar PDF -> honest, no hallucination | ✅ (25.6s) | 0 | — |  |
| Malformed PDF -> clean error | ✅ (0.3s) | 0 | — |  |
| Blank PDF -> empty, honest | ✅ (0.5s) | 0 | — |  |
| Huge --limit does not crash | ✅ (69.3s) | 3 | verbatim 100% · url 100% · art 100% |  |
