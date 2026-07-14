# Demo narration — word-for-word script (video voice-over + live demo practice)

_Short sentences, plain words, built to be spoken aloud. Practice it three
times and Thursday takes care of itself. Stage directions in [brackets].
Numbers in **bold** are the ones to hit precisely — everything else can be
paraphrased freely._

---

## Opening (30 seconds)

> This is SENTINEL. It reads trade legislation and maps it to the UN's RDTII
> framework — automatically.
>
> The core design rule is simple: **the AI never decides the score.**
> The AI finds the text and quotes it word for word. Fixed rules — written
> from the official methodology — turn that into a score. Every row can be
> audited in seconds.

[pause 2s]

## Scene: one command (1 minute)

[type: `python main.py --economy Singapore --pillar 6`]

> One command. Economy in, structured output out. No manual steps.
>
> While it runs: retrieval is seed-first. Verified official texts answer
> first, live crawling fills the gaps. So a short run by a reviewer never
> depends on a government website being up.

[open the CSV, point at columns]

> Every row: the indicator, the exact article, a verbatim quote, the official
> source URL. If a quote does not match the source character for character,
> the system rejects it. It never shows what it cannot prove.

## Scene: the scanned PDF (2 minutes) — THE required shot

[type the --pdf command with the India procurement order]

> This is a scanned image PDF from the judges' own sample kit. No text layer —
> just pictures of pages.
>
> The engine OCRs it, finds the provisions, and cites them.

[open output next to the PDF page]

> Here — the quote matches the scanned page. The OCR quality is measured,
> not assumed: this document scored a **6 percent** character error rate,
> and that number is recorded in the output.

## Scene: beyond the sample kit (1 minute)

> The tool also found **five** in-force laws that are not in the official
> inventory — for example, Queensland's Information Privacy Act, a state law
> the federal list does not cover. Each discovery is cached with its URL and
> a hash, and flagged for legal review. Finding new evidence is the judges'
> stated differentiator — ours comes with provenance.

## Scene: the benchmark (1.5 minutes) — the strongest card

[open docs/round2-meeting-report.md table]

> We went beyond the required scope. We executed the full methodology — all
> **61** indicators, all **12** pillars — across **seven** additional
> economies, and we benchmarked against the official database itself.
>
> **464** rows, end to end, fully automated. The engine found usable evidence
> in **78 percent**. And in **46 percent** of rows, its score matches the
> official evaluators exactly — across seven languages, including Thai,
> Mongolian, and Russian.
>
> To be clear about what that number means: this is a draft-for-review
> system. Scoring stays with the human researcher. 46 percent is how often
> the draft is already the final answer — with zero human help.

## Scene: cost + close (30 seconds)

> Cost: about **one to five cents** per economy per pillar, measured, printed
> with every run.
>
> Fresh clone, pip install, one command. Open-weight fallback if there is no
> API key. That's SENTINEL.

---

## Q&A one-liners (memorize these five)

- **"Why only 46%?"** — "Random guessing on this scale is about 22 percent.
  46 is fully automated with zero review — and our legal lead's verification
  session showed most remaining errors are judgement calls, not extraction failures."
- **"What if the model hallucinates?"** — "It can't put words in a law's
  mouth: quotes are verified character for character against the source, or
  the row is rejected."
- **"What about non-English laws?"** — "Same pipeline. Exact-match rates
  across seven languages all land between 41 and 57 percent — language was
  not the bottleneck."
- **"Can I run it?"** — "Fresh clone, pip install, one command, under ten
  minutes. There's also a Docker stack, and an offline mode with zero
  network."
- **"What's next?"** — "Three things: encode our legal lead's rulings into
  the scorer, wire the embedding store into retrieval, and Timor-Leste as
  the bonus economy."

## Rehearsal tips

1. Read it aloud twice slowly, once at speed. Total should land ≈ 7 minutes.
2. Do not memorize the prose — memorize the **bold numbers** and the scene
   order; say the rest your own way.
3. When a command is running, talk. Silence during a 30-second run feels
   like a failure even when it isn't.
4. If anything breaks live: "let me show you the offline mode" — it always
   works, and resilience IS one of the judged criteria.
