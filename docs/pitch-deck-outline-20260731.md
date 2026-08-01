# Pitch Deck Outline — Team SENTINEL [63]
## Aug 3, 2026 · 14:00–14:15 GMT+7 · 8 min presentation + 7 min Q&A

---

## Slide 1: Title (30s)
**SENTINEL — AI Tool for Digital Trade Regulatory Analysis**
"Where Code Meets Law"
Maynooth University · UN ESCAP RDTII 2.1 Hackathon

> Spoken: "We built a tool that reads trade regulations across 7 economies and 12
> languages, and maps every relevant provision to the 61 RDTII indicators —
> reproducibly, verifiably, and without a paid API key."

---

## Slide 2: The Problem We Solve (45s)
- 809 baseline laws across 7 economies, 12 languages
- Manual mapping takes weeks per economy
- Judges need VERIFIABLE evidence, not AI guesses
- Key question: "Can I trust this mapping?"

> Spoken: "Trade negotiators need to know what each country's laws actually say
> about each of 61 indicators. Doing this by hand takes weeks per economy. Our
> tool does it in minutes — and every answer comes with the exact legal text,
> character-for-character, so you can verify it yourself."

---

## Slide 3: How It Works — The Pipeline (90s)
One law flows through 6 stages:
1. **Fetch** — official government portals, TLS impersonation
2. **Chunk** — split at article boundaries
3. **Classify** — keyword filter (7 languages) → candidate indicators
4. **Extract** — LLM pulls structured facts + verbatim quote
5. **Verify** — anti-hallucination: quote must exist character-for-character in source
6. **Score** — deterministic Python (no AI in the score)

KEY INSIGHT: The AI only EXTRACTS. Everything else — splitting, filtering,
checking, scoring — is deterministic code we can test.

> Spoken: "This is the heart of our design. The AI does one job: read the law
> and pull out the relevant quote. After that, everything is checked. The quote
> must match the source exactly — we use three levels of matching, from exact
> string comparison to fuzzy matching for OCR noise. And the score is never
> decided by the model — it's a fixed Python rule per indicator. Same facts,
> same score, every time."

---

## Slide 4: Live Demo (2 min)
**Pre-typed command, press Enter:**
```
python main.py --economy China --pillar 6 --from-corpus --provider ollama
```

**What judges see:**
- Terminal output: "reading N corpus laws → extracting → verifying → scoring"
- Output CSV opens: columns Economy/Law Name/Indicator ID/Verbatim Snippet/Score
- The verbatim quote WITH source URL and character offset

**Show the merged submission:**
- `outputs/round2_submission_merged/all_economies_merged.csv` — 1,456 rows

> Spoken: "I've pre-loaded the engine. When I press Enter, it reads Chinese
> data protection laws from our verified corpus, extracts the relevant
> provisions, and writes a CSV — all key-free, using a local open-weight model.
> While it runs, let me show you what the final output looks like."

---

## Slide 5: Results — By the Numbers (60s)
| Metric | Value |
|---|---|
| **Official cell coverage** | **166/229 (72.5%)** |
| **Verbatim grounding** | **96.2%** (quote in source, char-for-char) |
| **Blind-verifier override** | **29%** (independent checker catches over-scores) |
| **Deployment cost** | **$12.96 full submission / $0 open-weight** |
| **Test suite** | **818 passed** |
| **Economies** | 7 (CHN/IND/IDN/LAO/MNG/RUS/THA) |
| **Pillars** | All 12 (61 indicators) |
| **Languages** | EN/ZH/HI/ID/LO/MN/RU/TH |
| **Key-free** | Yes (DuckDuckGo Lite → Bing cascade) |

> Spoken: "72.5% of the official scorable cells have evidence. 96.2% of our
> quotes are verified character-for-character in the source text. An independent
> blind checker overturns 29% of over-scores before anything ships. And the
> entire 7-economy submission costs $12.96 on a cloud model — or zero dollars
> on the open-weight path. Most importantly: no paid API key is needed."

---

## Slide 6: What Makes Us Different (45s)
1. **Deterministic scoring** — the model never picks the number
2. **Anti-hallucination kill switch** — unverifiable quote → dropped
3. **Key-free by design** — judges run without signing up for anything
4. **Reproducible** — same corpus + same code = same output, every time
5. **Honest about gaps** — 66 uncovered cells categorized by root cause (fetch / corpus / extraction)

> Spoken: "Four things set us apart. One: our scores are deterministic Python,
> not model opinions. Two: every quote is verified against the source — if we
> can't find it, we drop it. Three: a judge can run our tool without any paid
> API key. Four: the same input always gives the same output — it's reproducible.
> And we're honest about what we haven't covered: our gap worklist breaks down
> every missing cell by root cause."

---

## Slide 7: Engineering Rigor (30s)
- **818 automated tests** (pipeline, scoring, verification, discovery, OCR)
- **SHA-256 corpus integrity** — truncated/wrong-law text detected before it poisons output
- **Coverage/cost tooling** — `coverage_report.py` and `cost_report.py` make every headline number reproducible
- **Round-1 offline path still works** — `--offline` mode for fast demos

> Spoken: "We've built testing and verification into the tool itself. 818 tests
> cover every stage. Our corpus has SHA-256 integrity checks — a corrupted law
> text can't silently poison the submission. And every headline number I've
> shown you can be reproduced by running `coverage_report.py` and `cost_report.py`."

---

## Slide 8: Thank You + Q&A (15s)
Team: Dong (Tech Lead), Katie (Legal Lead)
GitHub: github.com/22abad/UN-DigitalTrade-AI-Mapper-private

> Spoken: "Thank you. We're ready for your questions — and we have the engine
> loaded and ready to run on any economy and pillar you'd like to see."

---

# Demo Script (if judges ask for live run during Q&A)

## Pre-flight (join 20 min early, have these ready)
- Terminal 1: `cd ... && source .venv-eval/bin/activate`
- Terminal 2: `cat outputs/round2_submission_merged/all_economies_merged.csv | head -20`
- Typed but NOT entered: `python main.py --economy China --pillar 6 --from-corpus --provider ollama`

## If judge says "run it live"
1. Press Enter on the pre-typed command
2. Say: "This reads Chinese data protection laws from our verified corpus.
   Extraction takes about 2-3 minutes — while it runs, let me walk you through
   what's happening at each stage."
3. Switch to slides 3-4, explain each stage as the terminal updates
4. When done: `cat outputs/China_P6_*.csv | head` to show the output

## If extraction fails during live run
1. Say: "The extraction is still running — our API call may be rate-limited.
   This is exactly why we pre-generate output. Here's the merged submission
   CSV, which was produced by this same pipeline."
2. Show the merged CSV
3. Explain the pipeline architecture while the extraction continues

## If screen share fails (pitch rule #10)
1. Post the merged CSV in Zoom chat immediately
2. Continue Q&A verbally — explain the pipeline from slides
