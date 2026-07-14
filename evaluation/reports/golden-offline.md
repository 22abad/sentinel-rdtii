# RDTII golden-set evaluation

- Mode: `offline`
- Commit: `dd979bb5519505f063e48ceaa0aa3cf99dafe905`
- Generated: `2026-07-14T16:25:49+01:00` (IST)
- Provider/model: `offline-fixture` / `offline-fixture-v1`
- Case-set SHA-256: `6ce558372bef2d8c0732194d6b6c940b651e54ac6d05f309b2a4e2ac3a7186bd`
- Cases evaluated: 8 across 5 documents

## Mapping and citation metrics

| Metric | Result |
| --- | ---: |
| Mapping precision | 100.00% |
| Mapping recall | 100.00% |
| Mapping F1 | 100.00% |
| Citation exact-match | 100.00% |
| Article citation accuracy | 100.00% |
| Raw score accuracy | 100.00% |
| Category score accuracy | 100.00% |
| Scope accuracy | 100.00% |

## Case-level failures

- False positives: 0
- False negatives: 0
- Explicit negative cases hit: 0
- Citation offset failures: 0

### Per-country metrics

| Group | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| AUS | 100.00% | 100.00% | 100.00% |
| MYS | 100.00% | 100.00% | 100.00% |
| SGP | 100.00% | 100.00% | 100.00% |

### Per-indicator metrics

| Group | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| 6.1 | 100.00% | 100.00% | 100.00% |
| 6.2 | 100.00% | 100.00% | 100.00% |
| 6.4 | 100.00% | 100.00% | 100.00% |
| 7.3 | 100.00% | 100.00% | 100.00% |

## Measured usage and cost

- Vision OCR calls: 0
- Vision calls with unavailable usage: 0
- Known Vision token subtotal: 0 input / 0 output
- Mapping LLM API cost: $0.000000
- Vision OCR API cost: $0.000000
- Search cost: $0.000000
- Known LLM + OCR subtotal: $0.000000
- Total API cost: $0.000000

## Stage timing

- Discovery: 0.000 seconds
- Fetch: 0.000 seconds
- PDF processing/OCR: 0.000 seconds
- Mapping: 0.141 seconds

## Reproducibility

- Runtime: 0.156 seconds
- Document-set SHA-256: `bd63aeb00f42975c2c4a4c81c48dd8e772c48e66415f4c4dc3e88b34c97d615a`
- Command: `python scripts/evaluate_golden_set.py --mode offline --output evaluation/reports/golden-offline.json`
- Machine-readable details are stored in the sibling JSON report.
