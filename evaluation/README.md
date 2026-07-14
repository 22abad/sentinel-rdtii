# RDTII Golden-Set Evaluation

This directory contains the versioned inputs for reproducible, provision-level
evaluation of the real RDTII extraction pipeline. It extends the official RDTII
data-collection fields (`Pillar_ID`, `Indicator_ID`, scores, Act/practice,
coverage, comments, timeframe, references, and note) with stable case IDs,
negative labels, exact evidence, input hashes, and legal-review metadata.

## Review boundary

All 29 labels and all 10 source records have substantive-lead approval. Each
approved record carries its review date, role, framework version, and review
notes. The runner continues to exclude any future pending labels by default;
`--include-pending` remains development-only and adds a warning to both report
formats.

The candidate set has a machine-checked structural contract: 25–40 cases, a
positive and boundary negative for every Pillar 6/7 indicator, and Pillar 6 and
7 coverage for AUS, MYS, and SGP. Run `make golden-coverage`. This structural
check is deliberately separate from legal approval. Run
`python scripts/check_golden_coverage.py --approved-only` to verify that the
approved subset independently satisfies the same contract.

## Files

- `golden/documents.jsonl`: document manifest, source provenance, fixture path,
  and SHA-256.
- `golden/cases.jsonl`: expected provision mappings and explicit negative cases.
- `schema/golden-case.schema.json`: portable case contract; Pydantic enforces the
  same contract at runtime.
- `fixtures/text/`: short reference excerpts, not redistributed full documents.
- `fixtures/offline-provider-responses.jsonl`: deterministic predictions stored
  separately from expected labels. The pipeline never copies expected answers
  into its predictions. Every classifier-selected indicator must explicitly
  contain either a `response` or `"no_mapping": true`; missing outcomes are
  reported as fixture-configuration failures.
- `reports/`: optional sanitized evidence reports. Routine local outputs should
  be written outside the repository or left uncommitted.

## Modes

### Offline

Runs fixed text through the production chunker, classifier, extraction
orchestrator, deterministic scorer, quote verifier, and mapping validator. The
only substituted boundary is the external model response.

```bash
python scripts/evaluate_golden_set.py \
  --mode offline \
  --output /tmp/evaluation-offline.json
```

The command fails when no approved cases exist, preventing accidental
publication of metrics based only on unreviewed labels.

### Live discovery

Runs official-only Discovery and reports document recall separately. It does
not calculate provision or mapping accuracy.

```bash
python scripts/evaluate_golden_set.py \
  --mode live-discovery \
  --countries AUS MYS SGP \
  --output /tmp/evaluation-discovery.json
```

### Full

Runs live official-only Discovery, fetches matched documents, then invokes the
configured real model and the production extraction pipeline.

```bash
python scripts/evaluate_golden_set.py \
  --mode full \
  --countries AUS MYS SGP \
  --provider deepseek \
  --output /tmp/evaluation-full.json
```

Live and paid modes are manual acceptance commands, not CI jobs.

Discovery, fetching, and extraction have bounded timeouts. Discovery and fetch
retry once only for timeouts, connection failures, HTTP 429, 502, or 503.
Defaults can be overridden with `RDTII_EVALUATION_DISCOVERY_TIMEOUT_SECONDS`,
`RDTII_EVALUATION_FETCH_TIMEOUT_SECONDS`, and
`RDTII_EVALUATION_EXTRACTION_TIMEOUT_SECONDS`.

## Matching policy

A correct mapping must match country, document, indicator, and normalized
evidence text with at least 0.80 similarity. Matching is one-to-one and prefers
the highest evidence similarity. Document-title matches alone never count as a
correct provision mapping. Citation exact-match additionally requires the
reported offsets to recover the exact predicted quote from the evaluated text.

Reports include commit SHA, timestamp/timezone, mode, provider/model, case and
document hashes, aggregate/per-country/per-indicator metrics, case-level false
positives and negatives, source failures, stage timing, runtime, and available
provider usage. Full-mode stage timing separates discovery, fetch, PDF
processing/OCR, and mapping. Provider token and API cost values come from actual
returned usage; unavailable values remain unavailable rather than becoming zero.

Page-level OCR CER benchmarking is documented separately in `ocr/README.md`.
