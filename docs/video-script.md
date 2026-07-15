# Round 1 submission video — shooting script (≤10 min)

**Official requirement (orientation deck, deliverable 4):** screen-recording
walkthrough of the *engine processing a scanned/image PDF document and
generating correct citations*. Max 10 minutes. Judges include non-technical
reviewers — narrate what they see, not the code.

**Recording setup:** clean terminal (large font, dark theme), repo at `main`,
`.env` configured. One take per scene is fine — scenes splice together.
Record rough cut today; teammates voice-over later, so **leave 2–3 s of
still frame at each scene boundary** and follow the on-screen beats below.

---

## Scene 1 — What the tool is (0:00–0:45)

Show: README top in the editor, then the architecture diagram / repo tree.

Voice-over beats:
- SENTINEL maps digital-trade legislation to RDTII 2.1 indicators:
  discovery → OCR/extraction → indicator mapping → deterministic scoring.
- Anti-hallucination contract: every output row carries a **verbatim quote**
  verified character-for-character against the source; the LLM never decides
  the score — deterministic Python does, citing the published criteria.

## Scene 2 — One command, judge's view (0:45–2:30)

Run (Round 1 mandatory scope, seed-first default):

```bash
python main.py --economy Singapore --pillar 6
```

Voice-over beats while it runs:
- One command: economy + pillar in, CSV + JSON out. No manual steps.
- Seed-first retrieval: verified cached official texts answer first,
  live discovery fills gaps — a judge's short run never gambles on a crawl.

Show when done: open the CSV — point at `indicator_id`, `verbatim_snippet`,
`source_url`, `discovery_tag` (KNOWN vs NEW).

## Scene 3 — THE REQUIRED SHOT: scanned PDF → citations (2:30–5:30)

Use the official sample-kit scanned document:

```bash
python main.py --economy India --pillar 2 \
  --pdf "requirements/Hackthon Knowledge Products/Database/Sample legislations/PDF of scanned documents/India-Public_Procurement_order_2017.pdf"
```

Voice-over beats:
- This is a **scanned image PDF from the judges' own sample kit** — no text
  layer. The engine OCRs it, chunks it, extracts, and cites.
- Open the output CSV next to the PDF page: **the verbatim snippet matches
  the scanned page text**; article/section reference and mapping rationale
  are right there for a legal reviewer.
- Note the OCR quality metadata in the JSON (`ocr_quality_cer`,
  `pdf_is_scanned: true`) — quality is measured, not assumed.

## Scene 4 — Beyond the sample kit: NEW evidence (5:30–7:00)

Show `data/law_library/manifest.jsonl` (or the discovery report):

- The tool independently found **5 genuine NEW laws** beyond the sample kit
  (e.g. Australia's Identity Verification Services Act 2023), each cached with
  URL + SHA-256 + pending
  legal-review flag. "Discovery of new evidence" is the judges' stated
  differentiator.

## Scene 5 — Optional scope: 12 pillars × 7 more economies (7:00–9:00)

Show `docs/round2-meeting-report.md` table, then run a quick targeted line
(or show the eval JSON if time is tight):

```bash
python tools/run_round2_eval.py --economy IND --pillar 7 --limit 2
```

Voice-over beats:
- Beyond the mandatory scope we executed the **full RDTII methodology — all
  61 indicators — across 7 additional economies**, and benchmarked against
  the official database itself: **500 rows, 351 evidence-backed (70.2%),
  251 exact score matches (50.2%), fully automated**, with a 36–60%
  exact-match band across seven languages
  including Thai, Mongolian and Russian.
- Every number in this table traces to a JSON report in the repo.

## Scene 6 — Close (9:00–9:45)

Show README Quick Start once more.

- Reproducible: fresh clone, pip install, one command; open-weight fallback
  (Ollama) if no API key. Deterministic scoring, verbatim citations,
  measured accuracy.

---

## Pre-flight checklist (before hitting record)

- [ ] `git status` clean, on `main`
- [ ] `.env` has DEEPSEEK_API_KEY; `RDTII_LLM_PROVIDER=deepseek`
- [ ] Dry-run Scene 2 & 3 commands once off-camera (cache warm, timing known)
- [ ] Terminal font ≥ 16 pt; hide personal notifications
- [ ] Have the scanned PDF open in Preview for the side-by-side in Scene 3
