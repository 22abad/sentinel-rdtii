# 决赛作战计划(Grand Finale, Bangkok Oct 2026)
_2026-08-03 晚立项。依据:`requirements/Hackathon Overview—Dr.Witada A.pdf` 全 20 页(决赛要求的权威来源)。无论 Aug 5 结果如何,按决赛标准把工具做完——这是简历工程的最终形态。_

## 一、决赛标准(官方原文提炼)

### 范围
- **决赛经济体**:R1 三国(SGP/AUS/MYS)+ 追加 8 国里**至少 3 国**:THA/CHN/IND/IDN/RUS/LAO/MNG(各 10 分)+ **Timor-Leste(20 分,官方指定 hard challenge)**。超出 3+3 = 加分。
- **Pillar 6+7 对所有经济体强制**;其他 pillar = 加分。
- **Zone 1(检索)+ Zone 2(结构化抽取)强制**;Zone 3(打分)= 加分。
- 官方点名的难点:非英语、网站无序、法律架构复杂、无单一法源库。

### 评分 40/30/30
| 块 | 内容 | 官方红线 |
|---|---|---|
| 40% Substantive | 指标映射正确;**NEW evidence 是主要差异化项**;引文保真(精确条+款,页码/锚点,官方直链) | 转述型引文 = 扣分;错引 = 扣分 |
| 30% Resilience | **live 官方门户自主爬取**;扫描 PDF OCR(错误率 <5%,保结构);端到端零人工 | **预下载 PDF = 爬取 0 分** |
| 30% Architecture | 模块化后端(改一个 config 换 LLM/OCR);每行 verbatim 审计链;实测成本 | LLM 硬编码 = FAIL |

### 评审动线(两种评委,都要秒级闭环)
- 政策评委:Excel 开 CSV → 筛 Discovery Tag=NEW → 读 Mapping Rationale(≤300 字符)→ 点 Source URL 对 verbatim → 打分
- 技术评委:clone → README 一条命令跑 → JSON 查 model_version 钉版本 → 查 ocr_quality_cer → **在 hold-out 经济体上重跑** → raw_context 查幻觉

## 二、现状对照(2026-08-03 EOD 实测)

| 决赛要求 | 现状 | 差距 |
|---|---|---|
| 3+3 国覆盖 | R1 三国 + 7 国已做(188/229 = 82.1%) | ✅ 远超强制线 |
| Timor-Leste 20 分 | 仅侦察笔记(docs/timor-leste-scouting.md,源站已探通) | ❌ **未做,最大单点增量** |
| P6+P7 全经济体 | P6 = 20/20 满;P7 = 18/22 | ⚠️ 差 4 格:IDN 7.1、LAO 7.3/7.4、RUS 7.3 |
| live 爬取适配器 | AUS/CHN/IND/IDN/LAO/MYS/SGP/THA 有 | ❌ **缺 RUS、MNG、TLS**(pravo.gov.ru IPS 接口今天已实证打通!) |
| OCR + CER 指标 | OCR 管线在;`ocr_quality_cer` 字段在但常为 None | ⚠️ 需在 OCR 路径填真值,基准 <5% |
| JSON 元数据 | 39 字段,含 raw_context/processing_time | ⚠️ corpus 路径 `model_version`/`source_pdf_path` 为空 |
| 官方直链 | 大部分 | ⚠️ 存在 garant.ru 等第三方 URL(RUS 6.3 实锤)→ 决赛扣分点 |
| 一条命令 README | 有,R1 版 | ⚠️ 决赛版需钉版本+开源 fallback 段落 |
| Zone 3 加分 | 确定性打分已建 ✅ | — |
| 成本实测 | 每 run 计量 ✅(今日 $21/全天) | — |

## 三、作战序列

### P0 — 决赛硬门槛(本周)
1. **RUS 适配器**(`pravo_ips.py`):今天实证的 `pravo.gov.ru/proxy/ips/?doc_itself=&nd=…&rdk=…` 接口 → 检索+现行版全文,cp1251 解码已趟平。爬取分从 0 → 满。
2. **MNG 适配器**(`legalinfo.mn`):侦察笔记记载可拿 640K 字符,detail/lawId 直链模式。
3. **TLS 经济体落地**(20 分):`timor_leste` 公报适配器(mj.gov.tl,葡语;DeepSeek 葡语强)+ 经济体注册(代码/语言/关键词葡语化)+ P6/P7 首跑。**纯 NEW discovery**(无官方 sheet)= 同时喂 40% 块的差异化项。
4. **官方 URL 保真 pass**:扫全部 merged 行,第三方域(garant/consultant/wikisource…)→ 换 manifest official urls 或降级进 Notes。
5. **JSON 补真值**:corpus 路径填 `model_version`(provider 实名)与 `source_pdf_path`(有 PDF 时)。

### P1 — 40% 块冲刺(下周)
6. **P7 清零**(4 格):IDN 7.1(MoCI 20/2016 已在库,batch 竞争类)、LAO 7.3/7.4(老挝文 OCR 文本)、RUS 7.3(126-FZ 时效检查——152-FZ 的 2006 版教训直接复用:先验证条款在不在文本里)。
7. **NEW-discovery live 跑**:决赛经济体逐个 live 爬取跑一轮,产出带 `NEW` 标签的行(评委第一个筛选动作就是它)。
8. **引文保真强化**:PDF 行补页码(location_reference),HTML 行补锚点。
9. **Hold-out 自测**:选一个从未调优的配置(TLS 天然是),端到端跑通并记录——技术评委的第 4 步就是这个。

### P2 — 交付物打磨(冲刺周)
10. README 决赛版:Setup 3-5 行 / 一条命令 / 输出说明 / 钉版本 / 开源 fallback,五段强制结构。
11. OCR CER 基准:扫描件样本测 CER,证 <5%,数字进 deck。
12. ≤10 分钟录屏:扫描 PDF → 正确引文全流程(决赛指定场景)。
13. Deck 按 40/30/30 重排:每页对准一个评分块,NEW/TLS/live-crawl 各给证据页。

### 执行原则
- 每步照旧:test-first、杀层重放、问题→修复进 engineering log + vault、里程碑 TG。
- 预算:DeepSeek 余量充足(今日 $21);TLS/live 跑量小。
- 时间表:P0 本周内;P1 下周;P2 等 Aug 5 结果后定强度(进了 = 全力;没进 = 按简历工程收尾,四个交付物照做)。

## 四、风险
- pravo.gov.ru IPS 无官方 API 文档,接口可能变;缓存已抓文本 + sha256 兜底。
- TLS 公报是 PDF 扫描件为主(葡语 OCR:tesseract `por` 包需装)。
- MNG 西里尔 OCR(`mon` 包)质量未知——先文本源,扫描件后置。
- "评委 hold-out 重跑"意味着不能有任何 economy 特判 hack——generalization 优先于单格得分。
