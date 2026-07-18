# Demo assets

Materials for the Round 1 demo video (deliverable #4: "engine processing a
scanned/image PDF, generating correct citations").

## `MYS_PDPA_scanned_demo.pdf`
An **image-based / scanned** copy of Malaysia's Personal Data Protection Act 2010
(rasterised from the official sample-kit PDF at 150 dpi — pages 20-27, the
substantive provisions). `pdftotext` returns **0 characters** — it has no
selectable text, so it forces the OCR path. Used to demonstrate OCR resilience.

Run:

```bash
python main.py --economy Malaysia --pillar 6,7 --pdf demo-assets/MYS_PDPA_scanned_demo.pdf
```

Verified output: Tesseract OCR at ~94% confidence (CER 0.062) → **6 article-level
P7 citations** with exact verbatim, e.g. Section 43(3) (a 21-day data-retention
duty, page 2), Section 44(1) (record keeping), Section 46, Section 47. Sample
output in `OCR_demo_output.csv`.

## `OCR_demo_output.csv`
The judge-format CSV produced by the command above — proof the scanned PDF yields
correct, auditable citations.
