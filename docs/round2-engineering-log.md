# Round 2 engineering log — problems met, root causes, fixes

_Companion to `docs/round2-meeting-report.md` (the numbers). This is the story
behind them: every material problem hit while standing up the 12-pillar ×
7-economy pipeline, its root cause, the fix, and the verification. PR numbers
link every claim to code._

## The plan (and where it stands)

| Step | Deliverable | Status |
|---|---|---|
| 1 | Official baseline extracted machine-readable (61 indicators, 809 laws, 1,707 URLs, official scores) | ✅ #72 |
| 2 | Schema/CLI extended to 12 pillars × 7 economies | ✅ #73 |
| 3 | Local full-text corpus of baseline laws | ✅ #74 (+#81 browser path) |
| 4 | Methodology-driven extraction + deterministic scoring for all 61 indicators | ✅ #75 |
| 5 | Self-evaluation harness vs official scores | ✅ #76 (+#80 windowing) |
| 6 | Full 7-economy evaluation run | ✅ complete |
| 7 | Meeting report generator | ✅ #82 |

**Design thesis carried over from Round 1:** the LLM never chooses a number.
It extracts *which published criterion* a provision matches (a categorical,
checkable fact) plus a verbatim quote that must match the source
character-for-character; deterministic Python maps criterion → published
score. Round 2 scales this to 61 indicators by generating both the extraction
spec and the scoring rule from the official methodology JSON — adding an
indicator is a data change, not a code change.

---

## Problems, root causes, fixes

### 1. The Round 2 scope was not what we assumed

**Problem.** Round 1 tooling covered Pillars 6–7 for Singapore/Malaysia/
Australia. The Round 2 database revealed the final round spans **all 12
pillars (61 indicators) across 7 new economies** (CHN, IND, IDN, LAO, MNG,
RUS, THA) — effective overlap with our tool: zero economies.

**Insight that saved the schedule.** The official Round 2 workbook already
contains, per economy, the act name, official reference URLs **and the
official raw score** for every filled indicator. Extracted properly (#72),
it is simultaneously (a) the KNOWN baseline + seed URLs, (b) the indicator
rulebook for the deterministic scorer, and (c) **free ground truth for
self-evaluation** — the same "inventory → corpus → seed-first" play we
validated in Round 1, plus an accuracy metric judges can check.

### 2. Excel mangled the official indicator ids

**Problem.** The methodology sheet stores some indicator ids as numbers:
4.10 arrives as "4.1", and the true 4.1 was typed "4.01" to survive
formatting; same for 12.01/12.1.

**Fix.** Data-driven normalisation verified against the category names
(4.01 = patents = RDTII 4.1; float 4.1 = trade secrets = 4.10; 12.01 =
foreign equity = 12.1), raw id kept as `source_id` (#72). Methodology and
inventory ids align with zero orphans; a guard test fails if they drift (#73).

### 3. `FeatureValue` rejected legitimate float features

**Problem.** The first full India evaluation stalled. Log diagnosis: the 5.3
spec declares `government_equity_percentage` as float; DeepSeek correctly
returned `23.15`; the schema union `bool | int | str` **lacked float**, so a
correct answer failed validation and spun the per-chunk repair loop.

**Fix.** `Union[bool, int, float, str]` (#78). Lesson: the bug had existed
since Round 1 — only full-scale runs on new material exposed it.

### 4. No LLM client timeout: one hung connection = 30 lost minutes

**Problem.** The eval "ran" for 28 minutes at 0.8% CPU with five ESTABLISHED
connections to the DeepSeek API and nothing progressing. The OpenAI SDK
default is 600 s per attempt × retries; a throttled/hung connection occupied
a concurrency slot for ~30 minutes, and `asyncio.wait_for` cannot cancel a
blocked call's socket.

**Fix.** Explicit `timeout` (default 90 s) and `max_retries` (default 1) on
the client, both env-tunable; chunk concurrency also env-tunable (#79).
Hangs became fast failures the pipeline already knows how to absorb.

### 5. DeepSeek v4 is a reasoning model — and that starved extraction

**Problem.** Persistent "Empty response from LLM" errors. Raw API probe
showed `finish_reason: length` with `content: ''` and
`completion_tokens_details.reasoning_tokens > 0`: **deepseek-v4-flash spends
the completion budget reasoning before emitting JSON**; on long legal prompts
it burned the entire budget (and minutes of latency) and returned nothing.

**Fix.** Probed the API for the switch; `{"thinking": {"type": "disabled"}}`
works. Wired into the provider via `extra_body` (re-enable with
`RDTII_DEEPSEEK_THINKING=on`). Health call went from hang/empty to **1.0 s
with correct JSON** (#79). For deterministic JSON extraction, reasoning added
cost and latency without adding accuracy — our accuracy comes from quote
verification + deterministic scoring, not model deliberation.

### 6. Long statutes: the operative clause is buried past any prefix cap

**Problem.** India P7 (our strongest pillar) scored **zero evidence on all 10
rows**. The fetched texts were fine — real 100–170k-char RBI/IFSCA directions.
The eval fed the model the first 60k chars; the retention clauses sit beyond
100k.

**Fix.** Relevance-selected windows: score 4k-char windows by the target
indicator's routing phrases, feed the best segments in document order up to
the budget (#80). **India P7: evidence 0/10 → 9/10, exact score matches 5/10.**

### 7. Scoring semantics: "no evidence" is a score, not a miss

**Problem.** Rows the official evaluators scored 0 were counted as our
misses when we extracted no qualifying evidence — but in RDTII terms, no
qualifying measure *is* score 0.

**Fix.** No-evidence rows score 0 in the comparison; evidence yield is
reported separately so the two effects stay visible (#80).

### 8. JS-only government portals cap corpus coverage

**Problem.** HTTP-path fetch coverage: THA 78%, LAO 72%, IND 49%, CHN 46%,
IDN 31%, **RUS 18%, MNG 15%** — garant.ru, legalinfo.mn, jdih.kominfo.go.id
render via JavaScript.

**Fixes.** (a) An inventory row's multiple reference URLs are tried in order,
so a dead primary link no longer loses the law (#74). (b) `--browser` enables
the Playwright route for JS portals (#81) — refetch in progress. (c) Failures
are recorded as `status=failed` in the manifest; coverage numbers are honest,
never padded.

### 9. Assorted traps that cost real time

- **Registry expected Postgres**: discovery imports hit `localhost:5433`
  unless `DISCOVERY_REGISTRY_BACKEND=file` — the judges' CLI sets it, custom
  scripts must too.
- **Manifest overwrite**: a `--economy`-filtered corpus run wiped other
  economies' manifest records; now merged by key (#81).
- **Buffered pipes**: `python | grep | tee` hides all progress for hours; use
  `python -u`.
- **Playwright/Chromium crash dialogs** (macOS "Python quit unexpectedly"):
  browser-path fetches crash occasionally; harmless (each crash is caught and
  skipped) but alarming — dismiss and let it run. HTTP-first remains the
  default for stability.

---

## Final numbers (full 7-economy overnight run)

**464 baseline rows evaluated end-to-end; evidence extracted for 366 (78%);
exact official-score match on 217 (46%).** Per economy (exact match | MAE):
RUS **57%** | 0.31, LAO **53%** | 0.38, THA **48%** | 0.44, CHN **47%** | 0.44,
MNG **44%** | 0.49, IND **43%** | 0.44, IDN **41%** | 0.47.

Two findings worth the meeting's attention:

- **Language is not the bottleneck we feared.** Exact-match rates across
  English, Chinese, Thai, Indonesian, Lao, Mongolian (Cyrillic) and Russian
  all land in the 41–57% band; Mongolia — the economy with the *least*
  digitised sources — reached 96% evidence yield once the browser path
  unlocked legalinfo.mn (100% corpus coverage), and Russian scored highest
  of all. The criterion-tier design travels across languages.
- **Residual error is now concentrated in criterion-tier judgement** (which
  numbered option fits), not in missing evidence — the right frontier for
  targeted spec tuning, and visible per pillar in the meeting report.

Operational note: a handful of dense Indonesian documents (one maps to 14
indicators) exceeded the 600 s per-document budget and are recorded as
timeouts rather than silently dropped; raising the budget for dense docs is
a cheap follow-up.

## What the meeting can claim

1. **The full official methodology is executable**: 61/61 indicators have a
   generated extraction spec and a deterministic, auditable scoring rule
   citing the published criteria (verified: a 49% e-commerce equity cap
   scores 1.0 on 12.1 with a verbatim quote, and is correctly *rejected* for
   3.1 because the official exception assigns e-commerce equity to P12).
2. **Accuracy is measured, not asserted** — against the official Round 2
   database itself, with coverage, evidence yield, exact-match rate and MAE
   per economy and per pillar (`docs/round2-meeting-report.md`).
3. **Every failure mode found became a shipped fix** (#72–#82), and the
   fixes are regression-tested (482-test suite green).
