# Demo PDFs — try the pipeline with no discovery or browser

Three ready-made runs for `--pdf` mode (mapping still uses the configured model):

```bash
# 1. Born-digital statute → normal mapping (Companies Act s.245 hits P7-I3 retention)
python main.py --economy Malaysia --pillar 7 --pdf data/demo_pdfs/mys-companies-act-50pages.pdf

# 2. Scanned, image-based PDF → OCR path (Tesseract; from the official sample kit)
python main.py --economy India --pillar 2 --pdf data/demo_pdfs/india-procurement-scanned.pdf

# 3. Honesty check: same statute, mismatched pillar → returns EMPTY, never hallucinates
python main.py --economy Malaysia --pillar 6 --pdf data/demo_pdfs/mys-companies-act-50pages.pdf --allow-empty
```

Provenance: `mys-companies-act-50pages.pdf` is the measured-cost benchmark
excerpt (see `data/benchmark/`); `india-procurement-scanned.pdf` is from the
hackathon's official sample kit ("PDF of scanned documents").
