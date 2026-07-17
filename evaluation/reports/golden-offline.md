# RDTII golden-set evaluation

- Mode: `offline`
- Commit: `f0ad4f8dc5255685542d36a6a557bfbfe724a6a0`
- Generated: `2026-07-17T01:16:40+01:00` (IST)
- Provider/model: `offline-fixture` / `offline-fixture-v1`
- Case-set SHA-256: `499cce05e40aed671202dd9be8189785d87a5700fdf5627e330e465a82d6fe25`
- Cases evaluated: 29 across 10 documents

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
| 6.3 | 100.00% | 100.00% | 100.00% |
| 6.4 | 100.00% | 100.00% | 100.00% |
| 6.5 | 100.00% | 100.00% | 100.00% |
| 7.1 | 100.00% | 100.00% | 100.00% |
| 7.2 | 100.00% | 100.00% | 100.00% |
| 7.3 | 100.00% | 100.00% | 100.00% |
| 7.4 | 100.00% | 100.00% | 100.00% |
| 7.5 | 100.00% | 100.00% | 100.00% |

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
- Mapping: 0.145 seconds

## Reproducibility

- Runtime: 0.162 seconds
- Document-set SHA-256: `e368f59449194ab7db4640e57353a043f0ad8c8a53d3be046c2394021900f125`
- Command: `python scripts/evaluate_golden_set.py --mode offline --output evaluation/reports/golden-offline.json`
- Machine-readable details are stored in the sibling JSON report.
