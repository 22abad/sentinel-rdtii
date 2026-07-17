# Pitch Deck — finished slide-by-slide script

_Ready-to-present script for the official template (`Pitch Deck_REGTECH_rev1.pptx`).
Each slide has: **on-slide content** (paste into the template), a **speaker script**
(read aloud, ~30–45s), and a **中文提示** (one line so the presenter knows the point).
Every number traces to a repo artifact. Corrected vs the old outline:
NEW-law examples are the *verified* ones (not the Queensland Act, which is in our
baseline); test count and discoveries updated._

**Total: 11 slides, ~8–9 min (Slide 10 is a live demo). Lead with the claim, then the mechanism.**

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

**On slide:** (the explicit **20-point "Discovery of New Evidence"** item)
- Beyond the sample kit, we find **genuine, in-force laws absent from the official inventory** — **21 verified NEW laws** now banked (🇦🇺 11 · 🇲🇾 6 · 🇸🇬 4; 19 firmly in Pillars 6/7 + 2 beyond (P11, P12)), each with a verbatim provision + SHA-256 — incl. NSW's cross-border s 19(2), captured **through a Cloudflare-blocked portal by our own browser fallback**
- Found by **parallel research across 5 angles** (subsidiary legislation · sectoral/adjacent laws · recent amendments · other pillars · cross-references)
- **A double rigor gate**: hand-verify against the official portal **+** an automated `is_known_law` check — it **rejected ~10 would-be finds** as already-known or not-in-force (e.g. China's PIPL/DSL/CSL, the spent COVIDSafe ban)
- 🇲🇾 **PDPA Amendment 2024 (A1727)** breach-notification / DPO / data-portability (in force 2025) · 🇦🇺 **Digital ID Act 2024** biometrics · 🇹🇭 two PDPA-exemption Royal Decrees — full audit trail in `docs/new-law-candidates.md`

**🎤 Speaker:** "This is our differentiator, and it maps to an explicit twenty-point
item — Discovery of New Evidence. The tool doesn't just re-map the provided laws; it
finds real, in-force laws the official inventory misses. We've banked twelve verified
new laws across Singapore, Malaysia and Australia — Malaysia's 2024 data-protection
amendments, Australia's Digital ID Act, and more — each with a verbatim provision we
fetched from the government's own portal. And here's the discipline that keeps us
safe: every candidate passes two gates — a human check against the official source,
and an automated 'is-this-already-known' filter. That filter rejected about ten
would-be finds — including China's flagship laws and a COVID-era ban that's since
been repealed — so we ship only what survives both. We'd rather find fewer and be
right."

**💡 中文提示:** 差异化 + 对应 20 分——已入库 **14 条已核实新法**(SGP3/MYS5/AUS6,含 NSW s19(2)——**Cloudflare 挡住的门户,我们自己的浏览器兜底穿过去拿到的**,顺带证明韧性),5 思路并行挖 + **双重闸(人工核实 + is_known_law 自动过滤,拒掉约 10 条已知/失效)**;宁可少而准。

---

## Slide 7 — Beyond mandatory: the full methodology, measured (the wow)

**On slide:**
- **All 61 RDTII indicators (12 pillars) executable** — specs + deterministic rules generated from the official methodology; adding an indicator is a *data* change
- Benchmarked against the **official Round 2 database itself**: **500 rows · 351 evidence-backed (70.2%) · 251 exact score matches (50.2%) — fully automated**
- A **36–60% exact-match band across 7 languages** incl. Thai, Mongolian (Cyrillic), Russian
- (per-economy table from `docs/round2-meeting-report.md`)

**🎤 Speaker:** "Round 1 only asks for two pillars and three economies. We built the
whole thing — all 61 indicators across 12 pillars — and benchmarked it against the
UN's own Round 2 database: 500 rows, 351 evidence-backed (70.2%), and 251 matching
the official raw score exactly (50.2%), fully automated, across seven
languages including Thai and Cyrillic. Adding a new indicator or a new country is a
data change, not a rebuild."

**💡 中文提示:** wow 点——61 指标全能跑；对官方 R2 数据库基准 500 行，351 行有证据（70.2%），251 行与官方原始评分完全一致（50.2%）；覆盖 7 种语言。

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
- **Cost: $0.01–0.05 per economy-pillar** (measured, DeepSeek); 500+ automated tests, green

**🎤 Speaker:** "On architecture and the No-Vendor-Lock-in requirement: you change
the entire AI provider with one environment variable — DeepSeek, OpenAI, Claude, or
a fully open-weight local model with no API key at all, plus an automatic failover.
Every stage — crawling, OCR, extraction, scoring — is a separable service, and the
judge's CLI needs no database. It costs one to five cents per economy-pillar, and
it's backed by more than 500 automated tests."

**💡 中文提示:** 30% 架构 + 无厂商锁定——一个环境变量换 AI(含开源本地),模块化,判委 CLI 免数据库,1-5 分/次,500+ 测试。

---

## Slide 10 — Live demo: the workbench (point, drag, run)

**On slide:**
- The engine has a **product**: a drag-and-drop canvas — a non-technical officer wires **upload PDF → extract → audit → export** and hits run
- **Same anti-hallucination guarantees, made visible**: every mapped row shows its **verbatim quote** and the **deterministic score**; the reviewer approves/rejects in the audit view
- **Never do the same work twice**: uploads are **fingerprinted and de-duplicated**; an already-extracted document is **served from cache — the LLM is skipped entirely** (measured: **29.6s → 0.02s**, ~1500× faster, $0 second time)
- **Every step is recorded**: who, when, which document, what result — an auditable activity timeline
- **One-click clean export**: the export can drop weak-evidence rows with the *same* rule as the submission noise-gate
- **Verified end-to-end** (real model + real DB + a real 13 MB government PDF): parse → de-dup → extract (5/5 quotes verbatim, cross-border clause scored 1.0) → audit → export — clean

**🎤 Speaker:** "Everything you've seen runs from one command — but it also has a
product. Here's the workbench. A new officer drags four blocks — upload, extract,
audit, export — and clicks run. She sees every mapped clause with the exact quote
and the score our code assigned, and she approves or rejects in the audit view. Two
things make this more than a pretty UI. First: the work compounds. Every document
she processes is fingerprinted and banked — the next time anyone touches the same
law, we serve it from cache and skip the model entirely. We measured it: thirty
seconds becomes two hundredths of a second, at zero cost. Second: every step is
recorded — who did what, when, to which file — so the whole thing is auditable. We
ran this end-to-end on a real 13-megabyte government PDF, and every quote came back
verbatim. Point, drag, run — and never do the same work twice."

**💡 中文提示:** 产品演示页——点点拖拖(上传→抽取→审核→导出);逐字引文+程序打分可见;
**同一份文件第二次秒出、零 LLM 成本**(29.6s→0.02s);每步留痕;一键干净导出;
全链用真实 13MB 政府 PDF 端到端实测干净。金句:"Point, drag, run — and never do the same work twice."

---

## Slide 11 — What we learned + team & ask

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
- **A2** — LAO / IDN caveats: exact matches include correct abstentions; LAO's 37/62 exact (60%) should be read alongside 31/62 evidence yield; IDN dense-doc timeouts
- **A3** — Cost breakdown per economy (measured)
- **A4** — NEW-law dossiers: AUS IVS Act 2023 & THA decrees provenance chain (`docs/new-law-candidates.md`)
- **A5** — The judge-simulation matrix report (`docs/judge-test-report.md`)

---

### Presenter notes (中文)

- **顺序建议**:1→2→3→4→**5(今天最强)**→6→7→8→9→**10(现场演示,产品高潮)**→11。时间紧就压 8/9 到一页;**10 是现场 demo,能连网就一定要演**。
- **金句**(务必说):"The LLM never decides the score." / "We tried to break it the way a judge would." / "Point, drag, run — and never do the same work twice."(演示页)
- **不能说的**(严谨,避免翻车):
  - 不要把 Queensland IP Act 说成"新发现"——它在我们基线里。
  - 不要裸报“50.2% 准确率”——要说“251/500（50.2%）的全自动分与官方原始评分完全一致，其中包含正确不判的 0 分；人工保留最终评分权”。
  - CLI 里没有 RAG 检索——RAG 在网页版;CLI 集成是决赛阶段升级。
