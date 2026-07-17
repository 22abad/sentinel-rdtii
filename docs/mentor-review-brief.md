# Mentor Review Session — team brief & run-of-show
# 导师评审 — 团队手册与临场流程(中英对照:英文照着念,中文看懂意思)

_Prepared for the on-campus review (Prof. Jiangyuan Fu, Prof. Joseph Timoney,
Prof. Qian Xiao, TAs, and the visiting private-trade-law guest professor from
Portugal). 90 minutes of mentor time; our job is to extract maximum actionable
feedback before the July 20 submission. Print this; assign presenters at the top._

_为校内评审准备(付教授、Timoney 教授、肖倩教授、助教,以及来访的葡萄牙国际私营贸易法客座教授)。
导师时间共 90 分钟;目标是在 7 月 20 日提交前榨取最多可执行的反馈。打印本文,开场先分配讲者。_

---

## Run of show (suggested, 30 min presentation + discussion)
## 流程安排(建议:30 分钟展示 + 讨论)

| Min | Segment | Presenter | Material |
|---|---|---|---|
| 0–3 | Problem & architecture in one picture | Dong | deck outline §1–3 |
| 3–8 | **Live demo**: `python main.py --economy Singapore --pillar 6` + scanned-PDF run | Dong | terminal (offline mode as backup) |
| 8–12 | Round 1 status: golden set signed off, 21 verified NEW laws, 582 tests | Abel | deck §4–5 |
| 12–18 | **The benchmark**: 500 rows vs official DB, 251 exact (50.2%) / 351 evidence-backed (70.2%), 7 languages | Dong | `round2-meeting-report.md` |
| 18–22 | Legal-in-the-loop: the legal reviewer's verification session + adjudication findings | the legal reviewer | her exported results |
| 22–25 | Engineering war stories (pick 2: reasoning-budget starvation, prefix-cap blindness) | Eric/Abel | engineering log §5–6 |
| 25–30 | Our questions to you (below) | all | — |

中文提示:前 3 分钟一张图讲完问题与架构;3–8 分钟现场演示(离线模式做备份,断网也能跑);
8–12 分钟报 Round 1 状态(**14 条已核实新法、570 个测试全绿**);12–18 分钟讲基准
(对官方数据库 500 行:251 行打分完全一致 50.2%、351 行有证据 70.2%,7 种语言);
the legal reviewer 讲法务复核;最后 5 分钟把我们的问题抛给导师——**问问题的 5 分钟才是今天的正餐**。

## The one-slide numbers (memorize)
## 一页数字(背下来)

- Round 1 mandatory: **done + legally signed off**; judge command runs in one line; $0.01–0.05 per economy-pillar.
- Beyond mandatory: **61/61 indicators executable; 500 official baseline rows
  benchmarked; 251 exact score matches (50.2%), 351 evidence-backed (70.2%),
  fully automated, across 7 languages (36–60% exact-match band, incl.
  Cyrillic Mongolian and Russian).**
- Every row: verbatim quote (char-verified), article ref, official URL, SHA-256 provenance.
- Discovery: **21 verified NEW laws** banked (AUS 11 · MYS 6 · SGP 4; 19 firmly in P6/7 + 2 beyond (P11, P12)) — incl. NSW's
  cross-border s 19(2), captured **through a Cloudflare-blocked portal by our own
  browser fallback**.

中文对照:①必答项已完成且法务签字,评委一行命令能跑,每"经济体×支柱"成本 1–5 美分;
②超纲:61 个指标全可执行,对官方库 500 行基准——251 行与官方打分完全一致(50.2%)、
351 行有证据(70.2%),全自动、7 种语言;③每行输出带逐字引文(字符级校验)、条款号、官方链接、
SHA-256 溯源;④已入库 **14 条核实新法**(新 3 / 马 5 / 澳 6),其中 NSW s19(2) 是
**穿过 Cloudflare 拦截、用我们自己的浏览器兜底抓到的**——这句必讲,是韧性的活证据。

## Latest hardening — talking points (all landed; all tested, all golden-safe)
## 最新加固 — 谈资(全部已合并、已测试、不伤 golden set)

_Frame: "we didn't just build it, we tried to break it the way a judge would."_

_定调一句:"我们不只是把它做出来,我们还用评委的方式去弄坏它。"_

- **We simulated the judge's *real* command** (`main.py --economy X --pillar 6,7`,
  default + live discovery — not our clean `--offline` path) and audited every row.
  It exposed that a naive run was **58% noise on Singapore** — clauses lifted from
  *trade agreements* (SAFTA, the AU–SG Digital Economy Agreement) and an IMDA
  *blog article*. We added golden-safe filters that drop out-of-scope sources,
  fragment quotes, foreign-jurisdiction mislabels (a Malaysia PDPA page the model
  tagged "Hong Kong PDPO"), and one-statute domination. Result: the judge's own
  command now yields clean domestic-law output — **SGP 26→8, MYS 30→9, AUS 19,
  zero noise** — verified against the 29-case golden set with **0 regressions**.

  中文:我们跑了评委的**真实默认命令**(在线发现,不是我们干净的离线路径),逐行审计,
  发现新加坡原始输出 **58% 是噪声**(条文抄自贸易协定、甚至一篇博客)。加了对 golden set
  零伤害的过滤器后,评委自己的命令产出全是干净国内法(SGP 26→8、MYS 30→9、AUS 19,零噪声,
  29 个法务批准案例零回归)。

- **A committed, reproducible submission sample** lives in
  `docs/r1-submission-sample/` (SGP/MYS/AUS × P6/P7, frozen 13-field schema).

  中文:可复现的提交样例已在仓库里(三国 × 两支柱,冻结的官方 13 字段格式)。

- **The engine now has a product, verified end-to-end.** The drag-and-drop
  workbench (upload → extract → audit → export) was tested through with a *real*
  model, a *real* database, and a *real* 13 MB government PDF (Nigeria DPA): PDF
  parse → **de-dup on re-upload** → extract (**5/5 verbatim quotes are exact
  source substrings — zero hallucination**; the cross-border clause scored 1.0) →
  audit approve → Excel export — clean. Differentiators, all landed and tested:
  (a) **document-level reuse** — an already-extracted document is served from
  cache and the LLM is skipped (**29.6s → 0.02s**, $0 the second time); every hit
  is logged. (b) A **general activity timeline** — who/when/which-file/result for
  ingest, extract, discover, review, export. (c) An opt-in **`drop_weak` clean
  export** applying the submission noise-gate rule. Tagline for the live demo:
  *"Point, drag, run — and never do the same work twice."*

  中文:引擎之上有产品了,端到端实测干净:上传→抽取→审核→导出,真模型+真库+真 13MB 政府 PDF;
  5/5 逐字引文零幻觉、跨境条款满分。三个差异化卖点:同一份文件第二次**秒出且零成本**
  (29.6 秒→0.02 秒,跳过大模型)、每步留痕的操作时间线、一键干净导出。
  金句:"Point, drag, run — and never do the same work twice."(点、拖、跑——同样的活不干第二遍。)

- **Genuine NEW evidence, independently verified** (the explicit **20-point
  "Discovery of New Evidence"** item at Stage 2):
  - **21 verified NEW laws now in the library** (AUS 11 · MYS 6 · SGP 4 — incl. the
    VIC/NT/NSW state cross-border acts that fill Australia's P6 gap), each with a
    verbatim provision fetched from the official government portal and a
    machine-checked SHA-256. Highlights: 🇸🇬 Banking Act 1970 s 47 (secrecy),
    Healthcare Services (General) Regs 2021 (retention); 🇲🇾 PDPA (Amendment) Act
    2024 (Act A1727) — breach notification s 12B, DPO s 12A, data portability
    s 43A, all in force 2025, plus PDP Regulations 2013; 🇦🇺 Digital ID Act 2024
    s 48 (biometrics), IVS Act 2023 s 10, NSW PPIP s 19(2).
  - **How we found them (say this):** parallel research passes per economy across
    5 angles (subsidiary legislation, sectoral/adjacent laws, recent amendments,
    other pillars, cross-references), then **a double rigor gate** — (1) hand
    re-verification against the official source and (2) an automated
    `is_known_law` check. The gate **rejected ~12 would-be finds** as
    already-known or not-in-force (e.g. China's PIPL/DSL/CSL, the Electronic
    Transactions Act, the spent COVIDSafe ban). We ship only what survives both.
  - 🇹🇭 two *PDPA exemption Royal Decrees* (2020/2023) — verbatim Thai pulled from
    the Office of the Council of State; corroborated by DLA Piper; English
    translations unofficial, pending Thai-reading legal review.
  - Full audit trail in `docs/new-law-candidates.md`.

  中文:新证据发现对应官方明说的 **Stage 2 的 20 分**。库里 **14 条核实新法**,每条都是官方门户
  抓的逐字条文 + SHA-256。挖法:每个经济体并行五个思路(子法规/部门法/近期修订/其他支柱/交叉引用),
  然后过**双重严谨闸**——人工对官方原文核实 + `is_known_law` 自动查重,拦下了约 12 条伪发现
  (中国三大数据法早在官方清单里、澳洲已废止的 COVID 条款等)。要传达的态度:**宁可少而准**。

- **Rigor discipline** (say this — mentors reward it): every filter is verified to
  drop **0 of 29 legally-approved golden cases**; each candidate is checked against
  an authoritative source before it is claimed; what can't be verified is flagged,
  not asserted. **570 automated tests, green.** And when a portal blocks automated
  clients, the tool now **reports it loudly to the user** (which strategies failed,
  and to verify in a regular browser) instead of silently skipping.

  中文:严谨纪律(一定要说,导师吃这套):过滤器实证不伤 29 个法务批准的 golden 案例;
  声称前必对权威来源核实;核实不了就标注、绝不硬说。**570 个自动化测试全绿。**
  门户拦截自动抓取时,工具会**大声告知使用者**(试了哪些策略、请人工浏览器核实),绝不静默跳过。

## Round 1 README readiness — audit vs the official template
## R1 提交 README 对照官方模板的差距审计(导师若问"提交材料齐了吗"就用这节)

_We audited the repo line-by-line against `requirements/README_template.md`.
Verdict: **the pipeline satisfies the template; the main README itself is being
rewritten in the template's structure — the #1 task before July 20.** Honest
per-item status below._

_我们把仓库和官方 README 模板逐行对了一遍。结论:**管线本身满足模板要求;
主 README 正在按模板结构重写——这是 7/20 前第一优先任务。**下面是逐项如实状态。_

- **"Economy + regulatory topic"** — the topic **is** the pillar: `--pillar 6` =
  cross-border data flows, `--pillar 7` = data protection; internally each pillar
  expands to topical + local-language query terms (`discovery/query_builder.py`)
  and site-scoped portal queries; finer grain via `--indicators 6.1 6.4`. ✅

  中文:官方说输入是"经济体+监管主题"——支柱**就是**主题,内部自动展开成主题词+当地语言词
  +按门户构造的搜索;更细用 `--indicators`。功能已有,README 会写明这层映射。

- **Economies covered — two honest tiers.** Tier 1 (live crawl + offline; judges
  can run directly): **SGP, MYS, AUS + THA, CHN** (the five in the live discovery
  registry). Tier 2 (live registries now configured + corpus-verified on 500 official
  rows): **IND, IDN, LAO, MNG, RUS** — each has an official-portal discovery
  registry with local-language terms (India Code / JDIH / Lao Gazette /
  Legalinfo.mn / pravo.gov.ru); depth still hardening for the finale.

  中文:覆盖经济体诚实分两档——第一档(实时爬取+离线,可直接跑):新马澳+泰中;
  第二档(仅离线/语料,已做 500 行基准):印度/印尼/老挝/蒙古/俄罗斯。决赛前补注册表升级第二档。

- **Env vars / stack:** the template's `LLM_PROVIDER=openai`, `OCR_ENGINE=azure`
  are fill-in examples; official Q&A allows any disclosed, Apache-2.0-compatible
  stack. Ours: `RDTII_LLM_PROVIDER=deepseek|openai|gemini|claude|ollama` (ollama =
  the no-API-key open-weight path the rubric rewards) and OCR = **Tesseract**
  (on the template's own option list — no Azure needed). ✅

  中文:模板的环境变量是示例填空,官方明说技术栈不限、披露即可。我们如实写自己的:
  provider 可一键切换(含免 key 的 ollama,评分标准明确给分),OCR 用 Tesseract(模板选项里本来就有)。

- **Template commands all work** ✅ — `--economy Singapore --pillar 6` →
  `outputs/Singapore_P6_[timestamp].csv/.json`; `--format {csv,json,both}`;
  `batch_run.py` at repo root; parameters genuinely change results (live-tested).

  中文:官方模板里那套命令全能跑——输出命名、`--format` 三选项、批量脚本都实测过。

- **Architecture, one honest divergence:** crawler / OCR / structural parsing /
  LLM mapping / 13-field writer all ✅; **RAG (hybrid retrieval) lives in the web
  workbench, not the CLI**. Official Q&A: architecture is "no prescription —
  design choices are scored" — our README draws our real diagram.

  中文:架构图一处要诚实——**RAG 检索在网页版,不在 CLI**。官方明说架构不做规定,
  README 画我们真实的图,绝不照抄模板图(评委一跑 CLI 就穿帮)。

- **Extended JSON metadata:** all six template fields present in
  `submission/schema.py` (`ocr_quality_cer`, `processing_time_seconds`,
  `raw_context_before/after`, `pdf_is_scanned`, `retrieval_method`) **plus six
  more** (retrieval_mode, final_url, http_status, fetch_method, model_version,
  source_file_sha256). A strength — say it proudly. ✅

  中文:官方要的 6 个扩展元数据字段**全有**,我们还多加 6 个(溯源更强)。加分项,大方讲。

- **Per-document cost table:** mechanism complete (`submission/cost.py`; measured
  $0.01–0.05 per economy-pillar); the template's per-component breakdown is being
  filled from one formal measured run before 7/20.

  中文:成本机制齐全、整体成本实测过;模板要的分项表(OCR/嵌入/大模型/爬取+token+秒数)
  正在跑一次正式测量填数,7/20 前完成。

- **Known Limitations we will write (honesty is a rubric item):** JS-heavy portals
  need our browser fallback (NSW proven; if even that fails the tool tells the
  user); THA translations unofficial pending review; sub-national instruments
  pending a methodology ruling (see the Portugal question); confidence is a
  *discovery* confidence, not a calibrated probability — rows < 0.80 flagged for
  human review; five Tier-2 economies offline-only.

  中文:要写的"已知局限"(诚实本身是评分项):JS 门户需浏览器兜底(NSW 已实证,连兜底都失败
  会明确告知用户);泰文翻译非官方待复核;州级法律计不计入国家指数待方法论裁定(正好问葡萄牙教授);
  置信度是发现置信度、<0.80 建议人工复核;第二档 5 国仅离线。

## Questions to ask each mentor (the real payload)
## 要问导师的问题(今天真正的收获)

**Prof. Timoney (CS/architecture):**

1. For the 3 Aug live pitch, which failure mode would you stress-test first —
   live crawling, OCR, or provider outage? (We have offline fallback; is that
   convincing or does it look like dodging?)
2. Is a 50.2% fully-automated exact-match rate against official evaluators a
   number to LEAD with or to contextualize carefully?

中文(Timoney,计算机/架构):①8/3 现场答辩您会先压测哪个失效点——在线爬取、OCR、还是模型服务商
宕机?我们有离线兜底,这算说服力还是像逃避?②"全自动 50.2% 与官方打分完全一致"这个数,
该当头炮报,还是要小心加语境?

**Prof. Qian Xiao (AI-assisted legal documents):**

1. Our residual error is criterion-tier judgement (restrictive vs
   empowering-only provisions). Any known techniques for legal-tier
   classification you'd point us to before the finale?
2. Does our "LLM extracts, deterministic code scores" split match how you'd
   audit an AI legal tool?

中文(肖倩,AI 法律文书):①我们的残余误差集中在"条款档位判断"(限制性 vs 仅授权性),
决赛前有没有值得看的法律档位分类技术?②"大模型只抽取、确定性代码打分"这个切分,
符合您审计 AI 法律工具的方式吗?

**Visiting private-trade-law guest professor (Portugal):**

_Coaching note for Dong(中文,只给你看):他是国际私营贸易法方向,未必懂 RDTII——没关系。
下面每一问都是我们**真实悬而未决的法律判断**,他答上任何一条我们净赚;答不上也不丢人,
因为问题本身就显示功课做足了。念法:每题先一句背景、再一句提问。你是在请教真问题,不是考他。
兜底:哪怕前四题都聊不动,第 5 题(东帝汶葡语样本)一定能接上——那是他的母语法域。_

1. **Sub-national laws in a national index.** "Australia's federal Privacy Act has
   no hard data-localization rule, but the state Acts we discovered — Victoria,
   Northern Territory, and NSW's s 19(2) — impose adequacy-style transborder
   restrictions on their public sectors. For a national-level index like RDTII,
   should sub-national instruments score the indicator at all? How do comparable
   exercises treat federal systems?"

   中文①(州法计不计入国家指数):澳洲联邦隐私法没有硬性本地化要求,但我们发现的三个州法
   对本州公共部门施加了"充分性测试"式跨境限制。国家级指数该不该给州级文书计分?联邦制国家
   在同类指数里通常怎么处理?——这直接决定我们 3 条澳洲新法怎么用,是真悬案。

2. **Exemptions: scoring direction.** "Thailand issued Royal Decrees (2020/2023)
   exempting broad categories of controllers from its PDPA. Our reading: an
   exemption instrument *lowers* the framework-completeness score — it is
   evidence about coverage, not about protection. Would you score it that way?"

   中文②(豁免法令的计分方向):泰国两个皇家法令把大类主体豁免出 PDPA。我们的读法是
   豁免文书应当**降低**框架完整度得分——它是"覆盖范围"的证据,不是"保护"的证据。您怎么看?
   ——泰国 2 条发现的计分方向就卡在这,the legal reviewer 的复核也在等。

3. **Constitutional right without implementing law.** "Timor-Leste's Constitution
   Article 38 guarantees personal-data protection and mandates a law to implement
   it — but that law has never been enacted (UNCTAD 2024 confirms the gap). For a
   'comprehensive framework exists' indicator, is a constitutional right with no
   implementing legislation a framework at all?"

   中文③(只有宪法没有实施法):东帝汶宪法 38 条保障个人数据保护并要求立法落实,但那部法
   20 多年没颁布(UNCTAD 2024 官方文件确认缺口)。对"是否存在综合框架"指标,光有宪法权利
   算不算框架?——他是葡语法律体系出身,东帝汶正是葡语法域,这题他大概率有真见解。

4. **Trade agreements vs domestic law (his home turf).** "Our noise filter drops
   provisions lifted from trade agreements — SAFTA, the Australia–Singapore
   Digital Economy Agreement — because RDTII scores *domestic regulation*. From a
   trade-law perspective: when a DEA data-flow commitment is transposed directly
   into domestic law, where exactly is the line between 'agreement' and 'domestic
   regulation'? Is our hard exclusion too blunt?"

   中文④(贸易协定 vs 国内法,他的主场):我们的噪声过滤器把贸易协定条文全部丢弃,因为 RDTII
   只给国内规制计分。但从贸易法角度:当数字经济协定的数据条款被直接转化进国内法,"协定"与
   "国内规制"的界线在哪?我们一刀切会不会切多了?——58% 噪声就是这么清出来的,这题最能让他发挥。

5. **(Closer / goodwill) Timor-Leste sample.** "The Jornal da República is in
   Portuguese — your native legal language. If we produce a 10-row Timor-Leste
   sample for the bonus economy, would you be willing to sanity-check it?"

   中文⑤(收尾拉关系):东帝汶官方公报是葡语——正好是您的母语法域。如果我们做出 10 行的
   东帝汶样本,能否请您把把关?——无论前面聊得如何,这句让他有台阶、我们有人情,法学院面子也有了。

**Prof. Fu:**

1. From the 45→20 cut: what typically kills teams at this stage — missing
   deliverables, unreproducible setup, or weak differentiation?

中文(付教授):45 进 20 的淘汰,通常死在哪——交付物缺项、环境跑不起来、还是差异化不够?

## Demo pre-flight (do before the session)
## 演前检查清单(评审前做完)

- [ ] `git pull`; `.env` has DEEPSEEK_API_KEY; ollama running as fallback
      / 拉最新代码;`.env` 有 key;ollama 兜底跑起来
- [ ] Rehearse: `python main.py --economy Singapore --pillar 6 --offline` (fast, deterministic)
      / 排练离线命令(快、结果确定)
- [ ] Rehearse the template's exact commands once: `--format both`, and
      `batch_run.py --economies Singapore Australia Malaysia --pillar 6 7`
      / 官方模板的命令原样排练一遍(评委可能照着模板敲)
- [ ] Scanned-PDF command ready in shell history (India procurement order)
      / 扫描 PDF 命令备在历史里
- [ ] Tabs open: `docs/r1-submission-sample/` (the clean output),
      `docs/new-law-candidates.md` (the discoveries), `docs/round2-meeting-report.md`
      / 浏览器开好三个标签:提交样例、新法档案、基准报告
- [ ] Optional wow: `docs/judge-test-report.md` (the graded judge-simulation matrix)
      / 可选彩蛋:评委模拟矩阵报告
- [ ] **Live workbench demo** (if the frontend + docker stack are up): upload a PDF →
      extract → audit → export; then **re-upload the same PDF to show instant reuse**
      (LLM skipped) and the activity timeline. Fallback if the UI isn't ready: the
      CLI + `docs/r1-submission-sample/` tell the same story.
      / 网页工作台演示:传 PDF→抽取→审核→导出;**再传同一份秒出**(跳过大模型)+ 操作时间线;
      前端没起就用 CLI + 样例讲同一个故事
- [ ] Formal cost measurement done (fills the README template's per-document
      cost table) / 正式成本测量跑完,README 模板的分项成本表填上数
- [ ] If campus wifi fails: everything above runs offline
      / 校园网挂了也没事:以上全部可离线

## What NOT to claim
## 不能说的话(严谨红线,说错当场翻车)

- Do not say "50.2% accuracy" bare — say "251 of 500 fully-automated scores match
  the official evaluators exactly; the tool is a draft-for-review system, and
  scoring stays with the human researcher per the official Zone 3 guidance."

  中文:不要裸报"50.2% 准确率"——要说"500 行全自动输出中 251 行与官方评估员打分完全一致;
  工具定位是草稿供人复核,最终评分权在人,符合官方 Zone 3 指引"。

- Do not claim RAG retrieval in the CLI — say the embedding store is live in
  the web app; CLI integration is a finale-stage upgrade.

  中文:不要说 CLI 里有 RAG 检索——RAG 在网页版,CLI 集成是决赛阶段升级。

- Do not claim live crawling for IND / IDN / LAO / MNG / RUS — those are
  offline/corpus-verified (Tier 2). Live registries cover SGP/MYS/AUS/THA/CHN only.

  中文:不要说印度/印尼/老挝/蒙古/俄罗斯支持实时爬取——那五国目前只有离线/语料路径,
  实时注册表只覆盖新马澳泰中。

- Do not present the THA Royal-Decree English translations as official — the Thai
  is verbatim from the Council of State; our English is unofficial, pending review.

  中文:泰国御令的英文翻译不要说成官方译文——泰文原文是官方逐字,英文是我们的非官方翻译,待复核。

- Do not hard-claim the VIC/NT/NSW state acts as *national* evidence until the
  sub-national methodology question (Portugal Q1) is settled — present them as
  "state-level cross-border instruments, methodology ruling pending."

  中文:三个州法先别硬说成国家级证据——等葡萄牙教授那题有说法前,统一口径是
  "州级跨境文书,方法论裁定待定"。

- Exact matches include correct abstentions. For LAO, say "37/62 exact (60%),
  with evidence found for 31/62" rather than treating exact match as extraction
  accuracy.

  中文:"完全一致"里包含"正确弃权"。讲老挝要说"62 项中 37 项一致(60%),其中 31 项找到证据",
  不要把一致率当成抽取准确率。
