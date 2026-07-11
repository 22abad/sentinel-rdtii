# RDTII Golden-Set Evaluation

This directory contains the versioned inputs for reproducible, provision-level
evaluation of the real RDTII extraction pipeline. It extends the official RDTII
data-collection fields (`Pillar_ID`, `Indicator_ID`, scores, Act/practice,
coverage, comments, timeframe, references, and note) with stable case IDs,
negative labels, exact evidence, input hashes, and legal-review metadata.

## Review boundary

All initial candidate labels are `review.status=pending`. They are grounded in
official workshop materials and primary legal sources, but they are not an
approved Golden Set until the substantive lead confirms the legal conclusion,
scope, score, source status, and framework version. The runner excludes pending
labels by default. `--include-pending` is development-only and adds a warning to
both report formats.

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
  --include-pending \
  --output /tmp/evaluation-offline.json
```

Omit `--include-pending` for submission evidence. The command will fail until
at least one case has been approved, which prevents accidental publication of
unreviewed accuracy claims.

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
positives and negatives, source failures, runtime, and available provider usage.
