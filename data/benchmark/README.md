# Cost benchmark document

`benchmark_50pages.pdf` is a 50-page excerpt (≈1,700 chars/page) of an official
statute, used to measure real per-document processing cost.

- **Source:** Companies Act 2016 (Act 777), reprint — Companies Commission of
  Malaysia (SSM), `https://www.ssm.com.my/pages/legal_framework/document/act%20777%20reprint.pdf`
- **Excerpt:** 50 consecutive pages spanning the record-keeping provisions
  (including s.245, the seven-year retention rule → RDTII indicator 7.3), so the
  run exercises a real Pillar-7 mapping.

Reproduce the measured cost:

```bash
python tools/cost_logger.py --pdf data/benchmark/benchmark_50pages.pdf \
    --economy Malaysia --pillar all
# → logs/cost_report.json
```

The measured headline numbers are reported in the root `README.md`
("Actual Cost Per Document").
