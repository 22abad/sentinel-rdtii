# Demo assets

Materials for the Round 1 demo video (deliverable #4: "engine processing a
scanned/image PDF, generating correct citations").

## `MYS_Pekeliling_scanned_demo.pdf` ← primary OCR demo
An **image-only / scanned** copy of Malaysia's Circular of the Personal Data
Protection Commissioner No. 1 of 2025 (Pekeliling DPO 1/2025, in **Malay**),
rasterised at 300 dpi from the official PDF. `pdftotext` returns ~0 characters
— no text layer, so it forces the OCR path.

Run:

```bash
python main.py --economy Malaysia --pillar 7 --pdf demo-assets/MYS_Pekeliling_scanned_demo.pdf
```

Verified output (2026-07-19): `pdf_is_scanned: true`, **5 article-level P7-I4
rows with exact Malay verbatims** (Seksyen 12A, Section 4(1), Paragraph 7(1), …),
correct bilingual instrument name, measured cost ≈ $0.01. One command covers
three claims at once: scanned input, non-English law, NEW discovery.

Note on `ocr_quality_cer` (~0.10 here): the metric is a confidence-derived
*estimate*, and Tesseract's English model under-reports confidence on Malay
text — the extracted verbatims themselves match the source. Quote per-page
confidence, not this proxy, when presenting.

## `MYS_PDPA_scanned_demo.pdf` (superseded as demo — kept for regression)
Scanned excerpt (pp. 20–27) of Malaysia's PDPA 2010, 150 dpi. ⚠️ Because the
excerpt has **no title page**, the document self-title corrector can latch onto
another Act named in the body (observed 2026-07-19: rows labelled "Private
Healthcare Facilities and Services Act 1998" with an empty Article column). Do
not use it on camera until the mid-document-excerpt case is fixed; use the
Pekeliling scan above instead.

## `OCR_demo_output.csv`
Judge-format CSV from the 2026-07-18 PDPA-scan run (pre-#300-series gate
pipeline) — historical sample only.
