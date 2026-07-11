# OCR CER benchmark

This benchmark compares page extraction output with a separately stored reference
transcription. Formal runs include only cases whose reference is marked
`human_corrected` and approved by an OCR benchmark reviewer.

The initial entries are candidate pages from the supplied workshop resource
library. Their references are machine-prepared drafts and remain `pending`.
They exist to select and prepare representative pages; metrics produced with
`--include-pending` are development-only and must not be cited as measured OCR
quality until a human checks every character against the rendered page.

The source PDFs are intentionally not copied into the repository. The manifest
stores their SHA-256 values and paths relative to the supplied resource bundle.

```bash
python scripts/benchmark_ocr.py \
  --source-root /path/to/drive-download-20260626T101049Z-3-001 \
  --include-pending \
  --output /tmp/ocr-cer-development.json
```

Remove `--include-pending` for a formal run. That command will refuse to run
until at least one human-corrected reference has been approved.

## Runtime and cost benchmark

Use the direct-document benchmark for the approximately 50-page primary-stack
and local/open-weight comparison. Run the same URL and commit with different
providers and keep the reports outside the repository until they have been
reviewed and sanitized.

```bash
python scripts/benchmark_document.py \
  --source-url https://official.example/legal-instrument.pdf \
  --document-id representative-50-page-law \
  --provider deepseek \
  --output /tmp/benchmark-primary.json

python scripts/benchmark_document.py \
  --source-url https://official.example/legal-instrument.pdf \
  --document-id representative-50-page-law \
  --provider llama-3-local \
  --output /tmp/benchmark-local.json
```

The report keeps mapping LLM cost, Vision OCR cost, and search cost separate.
Direct-source runs have no search call, so search cost is verifiably zero.
Tesseract and PyMuPDF consume no LLM tokens. If Vision fallback is enabled,
configure the pricing snapshot used for actual returned token counts:

```text
OPENAI_VISION_MODEL
OPENAI_VISION_INPUT_USD_PER_MTOK
OPENAI_VISION_OUTPUT_USD_PER_MTOK
OPENAI_VISION_PRICING_DATE
```

If those prices or provider token counts are absent, cost remains `Unavailable`.
Local-provider reports include OS/architecture and stage runtime even when API
cost is zero; they do not claim that local compute is operationally free.
