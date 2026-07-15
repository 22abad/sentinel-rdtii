# Pitch Deck — finished slide-by-slide script

_Ready-to-present script for the official template (`Pitch Deck_REGTECH_rev1.pptx`).
Each slide has: **on-slide content** (paste into the template), a **speaker script**
(read aloud, ~30–45s), and a **中文提示** (one line so the presenter knows the point).
Every number traces to a repo artifact. Corrected vs the old outline:
NEW-law examples are the *verified* ones (not the Queensland Act, which is in our
baseline); test count and discoveries updated._

**Total: 10 slides, ~7–8 min. Lead with the claim, then the mechanism.**

---

## Slide 1 — Title

**On slide:**
- Title: **SENTINEL — AI Regulatory Analysis for Digital Trade**
- Subtitle: *Reading trade law at machine speed, with evidence a lawyer can trust.*
- Team SENTINEL · Maynooth University · UN RDTII Hackathon
- (logo.png)

**🎤 Speaker:** "We're Team SENTINEL. We built an AI system that reads a country's
digital-trade regulation and maps it to the UN's RDTII indicators — automatically,
but with a verbatim evidence trail a human researcher can audit in seconds."

**💡 中文提示:** 开场——我们做了个"读法律、映射到 RDTII 指标"的 AI,但每条都有可核实的原文证据。

---

## Slide 2 — The problem

**On slide:**
- ~100 pages of unstructured, multilingual regulation **per economy**
- Today: researchers hand-search portals → hand-extract provisions → hand-map to indicators
- **Slow · unrepeatable · error-prone** — and it must be redone every cycle
- (Rubric anchor: this is exactly the automation the judges asked for — Zones 1 & 2)

**🎤 Speaker:** "Scoring one economy means a human reading around a hundred pages
of law, in several languages, finding the few provisions that matter, and mapping
each to an indicator. It's slow, it can't be reproduced, and it has to be redone
every assessment cycle. That's the bottleneck the RDTII team wants automated."

**💡 中文提示:** 痛点——每国 ~100 页多语种法律靠人手读、手抽、手映射,慢、不可复现、易错。

---

## Slide 3 — Solution in one picture

**On slide:**
- Pipeline diagram: **discover → fetch / OCR → extract → verify verbatim → deterministic score → 13-field CSV/JSON**
- One command: `python main.py --economy Singapore --pillar 6,7`
- **Tagline: "The LLM never decides the score."**

**🎤 Speaker:** "Here's the whole system in one line. We discover the official law,
fetch or OCR it, the model extracts the relevant clause, we verify that clause
exists character-for-character, and then deterministic code — not the model —
assigns the RDTII score. One command produces a standard 13-column table. The key
idea: the language model never decides the score."

**💡 中文提示:** 一张图讲完流程;记住金句"AI 从不决定分数"(分数由程序算)。

---

## Slide 4 — Anti-hallucination architecture (the 40% accuracy story)

**On slide:**
- Every row carries a **verbatim quote, verified character-for-character** — unverifiable mappings are **rejected, not shown**
- Deterministic Python maps the extracted criterion → the published RDTII score, citing the official criteria text (auditable in seconds)
- SHA-256-verified law cache; NEW/KNOWN reconciled against the official ESCAP Legal Inventory
- **Golden set: 29 legally-approved cases; every quality filter verified to drop 0 of them**

**🎤 Speaker:** "This is our accuracy story. Three guarantees. One: every row has a
quote we've checked appears verbatim in the source — if we can't verify it, we drop
it rather than show it. Two: the score comes from deterministic code citing the
official criteria, so a reviewer can audit it in seconds. Three: we have a
legally-approved 'golden set' of 29 cases, and every noise filter we add is proven
to leave all 29 untouched. We don't guess — we verify."

**💡 中文提示:** 40% 准确分的故事——逐字校验、程序打分、29 个法务批准案例做安全网。

---

## Slide 5 — We tried to break it like a judge would (resilience + accuracy)

**On slide:**
- We ran the **judge's real default command** (live discovery, not our clean offline path) and audited every row
- It exposed **58% noise on Singapore** — clauses lifted from *trade agreements* and an *IMDA blog article*
- We added **golden-safe filters** (out-of-scope sources, fragments, foreign-jurisdiction mislabels, one-statute domination)
- Result: the judge's own command now yields clean domestic-law output — **SGP 26→8 · MYS 30→9 · AUS 19 · zero noise**, with **0 golden regressions**

**🎤 Speaker:** "We didn't just build it — we tried to break it the way a judge
would. We ran the exact one-line command a judge runs, with live discovery on, and
audited every row. A naive run was 58% noise on Singapore: clauses pulled from
trade agreements, even a blog article. So we built filters — all proven safe
against the golden set — that keep only genuine domestic law. The judge's own
command now returns clean output for all three economies, zero regressions.
That's the difference between a demo and a submission."

**💡 中文提示:** 今天最强的谈资——模拟评委真实命令,发现 58% 噪声,已清干净(SGP 26→8等),0 golden 回归。

---

## Slide 6 — Discovery of NEW evidence (the differentiator)

**On slide:**
- Beyond the sample kit, we find **genuine, in-force laws absent from the official inventory** — each independently verified
- 🇦🇺 **Identity Verification Services Act 2023** (P7-I5) & **Privacy Amendment (Public Health Contact Information) Act 2020** — confirmed *in force* via the Federal Register API
- 🇹🇭 **two PDPA-exemption Royal Decrees (2020 / 2023)** — verbatim provisions from the Office of the Council of State; corroborated by DLA Piper
- **We retract the model's over-tagged indicators rather than ship them** — full audit trail in `docs/new-law-candidates.md`

**🎤 Speaker:** "This is our differentiator. The tool doesn't just re-map the
provided laws — it discovers real, in-force laws the official inventory misses. In
Australia, the 2023 Identity Verification Services Act and the COVID-app-data
Privacy Amendment — both confirmed in force through the government's own register
API. In Thailand, two Royal Decrees that exempt agencies from the PDPA, with the
verbatim Thai text pulled from the Council of State. And crucially: where the model
over-tagged an indicator, we retracted it rather than ship a wrong claim. Every
lead is verified before we make it."

**💡 中文提示:** 差异化——发现官方清单外的真新法(AUS 2 + THA 2),都独立核实过;过度声称的指标我们撤回不硬交。

---

## Slide 7 — Beyond mandatory: the full methodology, measured (the wow)

**On slide:**
- **All 61 RDTII indicators (12 pillars) executable** — specs + deterministic rules generated from the official methodology; adding an indicator is a *data* change
- Benchmarked against the **official Round 2 database itself**: **464 rows · 78% evidence yield · 46% exact score agreement — fully automated**
- Consistent **41–57% across 7 languages** incl. Thai, Mongolian (Cyrillic), Russian
- (per-economy table from `docs/round2-meeting-report.md`)

**🎤 Speaker:** "Round 1 only asks for two pillars and three economies. We built the
whole thing — all 61 indicators across 12 pillars — and benchmarked it against the
UN's own Round 2 database: 464 rows, 78% of them evidence-backed, 46% matching the
official human score exactly, fully automated, and it holds up across seven
languages including Thai and Cyrillic. Adding a new indicator or a new country is a
data change, not a rebuild."

**💡 中文提示:** wow 点——61 指标全能跑,对官方 R2 数据库基准 464 行/78% 证据/46% 精确,7 语种稳定。

---

## Slide 8 — Technical resilience (the 30% resilience story)

**On slide:**
- Live portal crawling + **Wayback fallback** + browser path for JS-only portals (Mongolia's legalinfo.mn: 15% → **100% corpus coverage**)
- **OCR** on scanned PDFs with a measured error rate per row
- **Failure containment**: one bad source never aborts a run; every failure is recorded, never hidden
- **Offline mode = same pipeline, zero network** — a judge's 10-minute run is never hostage to a live crawl
- **Built for a live demo**: real-time dual progress bars (overall + current step) narrate every document as it's read/extracted — English, in-terminal, never a silent hang

**🎤 Speaker:** "Resilience is 30% of the score, so we engineered for the bad day.
JavaScript-only portal? We drive a browser. Page gone? We hit the Wayback Machine —
that took Mongolia from 15 to 100% coverage. Scanned PDF? OCR with a measured error
rate. One source fails? It's logged and the run continues. And the whole pipeline
runs fully offline from a verified cache — so a judge on bad campus wifi still gets
a clean, identical result. And you'll see it working — live progress bars narrate
every step, so it never looks frozen."

**💡 中文提示:** (演示时可指着进度条说)实时进度条,读到哪部法、抽取到第几篇,一目了然,不会像卡死。

**💡 中文提示:** 30% 韧性——浏览器抓 JS 站、Wayback 兜底、OCR、单点失败不崩、离线可复现。

---

## Slide 9 — Architecture & no vendor lock-in (the 30% architecture story)

**On slide:**
- Swap the LLM by one env var (`RDTII_LLM_PROVIDER`): DeepSeek / OpenAI / Gemini / Claude / **Ollama open-weight, no API key**; automatic failover provider
- Modular: crawler · OCR · extraction · scoring · submission are separable services; **DB-free CLI for judges**
- **Cost: $0.01–0.05 per economy-pillar** (measured, DeepSeek); ~530 automated tests, green

**🎤 Speaker:** "On architecture and the No-Vendor-Lock-in requirement: you change
the entire AI provider with one environment variable — DeepSeek, OpenAI, Claude, or
a fully open-weight local model with no API key at all, plus an automatic failover.
Every stage — crawling, OCR, extraction, scoring — is a separable service, and the
judge's CLI needs no database. It costs one to five cents per economy-pillar, and
it's backed by about 530 automated tests."

**💡 中文提示:** 30% 架构 + 无厂商锁定——一个环境变量换 AI(含开源本地),模块化,判委 CLI 免数据库,1-5 分/次,~530 测试。

---

## Slide 10 — What we learned + team & ask

**On slide:**
- **Engineering discipline**: every failure mode we found became a merged, tested fix — including a dependency gap that would have given a judge *zero output* on a clean install
- **Rigor**: verify before we claim; flag what we can't verify; retract over-claims
- Team: tech lead · substantive lead · legal reviewer
- Roadmap to the finale: close the criterion-tier gap · human-review workflow · broaden economy coverage
- **Ask:** [your specific ask to the judges/mentors]

**🎤 Speaker:** "What we learned: the gap between a demo and a real tool is the
failure modes you find and fix. We found a dependency gap that would have handed a
judge zero output on a clean install — and fixed it, with a test so it can't come
back. Our discipline is simple: verify before we claim, flag what we can't, and
retract over-claims rather than ship them. We're a three-person team — engineering,
substance, and legal review — and we're ready for the finale."

**💡 中文提示:** 收尾——工程纪律(每个失败都变成带测试的修复)、严谨(核实再声称)、团队 + 下一步。

---

## Q&A appendix slides (have ready, do NOT present)

- **A1** — Full per-pillar accuracy rollup table (`docs/round2-meeting-report.md`)
- **A2** — LAO / IDN caveats: LAO's 53% = 15 evidence-backed + 18 correct abstentions; IDN dense-doc timeouts
- **A3** — Cost breakdown per economy (measured)
- **A4** — NEW-law dossiers: AUS IVS Act 2023 & THA decrees provenance chain (`docs/new-law-candidates.md`)
- **A5** — The judge-simulation matrix report (`docs/judge-test-report.md`)

---

### Presenter notes (中文)

- **顺序建议**:1→2→3→4→**5(今天最强)**→6→7→8→9→10。时间紧就压 8/9 到一页。
- **金句**(务必说):"The LLM never decides the score." / "We tried to break it the way a judge would."
- **不能说的**(严谨,避免翻车):
  - 不要把 Queensland IP Act 说成"新发现"——它在我们基线里。
  - 不要裸报"46% 准确"——要说"46% 的全自动分与官方精确一致,人工保留最终评分权"。
  - CLI 里没有 RAG 检索——RAG 在网页版;CLI 集成是决赛阶段升级。
