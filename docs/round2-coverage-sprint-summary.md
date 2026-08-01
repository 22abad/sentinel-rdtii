# Round 2 覆盖攻坚 — 工作进展总结

日期:2026-07-31(08-01 过夜批注更新)
目标:7 经济体 × 12 支柱 (229 个可计分单元格) 覆盖率最大化

---

## 〇、08-01 过夜 DeepSeek flash 批跑(最新)

| 指标 | 数值 |
|---|---|
| **当前覆盖率** | **166/229 (72.5%)** — 163→166,+3 格 (CHN +2, LAO +1) |
| 新 provisions | **242** (DeepSeek flash: CHN 57, IDN 77, IND 33, LAO 31, MNG 4, RUS 18, THA 22) + LAO qwen 补跑 4 |
| merged 总行数 | 1,456 (官方 13 列格式,`outputs/round2_submission_merged/`) |
| 剩余缺口 | 63 格 = EXTRACTION 38 + CORPUS_QUALITY 14 + FETCH_GAP 11 |
| 成本 | deepseek-v4-flash 批跑,预算内 (~90 RMB 目标) |

**关键结论(诚实):** 242 个新 provisions 只带来 +3 格 —— 大部分落在已覆盖格上。
DeepSeek 在同一 corpus 上重跑的边际收益已尽;**剩余缺口的瓶颈在 corpus 内容
(缺文本/文本质量),不在提取模型。** 后续提升必须先补文本。

**过夜事故:** auto_fix_corpus 把 Wayback UI 壳当法律文本存了 11 格(43 次抓取
同一 2,770 字符页面)。已闭环:manifest 手术清理、垃圾文件删除、疫苗
(`is_garbage_page` 双重拦截)、CHN 输出审计 0 行污染。详见工程日志同日条目。

**LAO "Decision" 门问题(待办):** no-statutory-word 门丢弃了 "Decision on
Electronic Signatures No. 1101/MPT 2021" ×3 行 —— 但 Decision 是老挝官方
inventory 内的正式文书类型,门误杀官方清单法。需给 LAO 加 "Decision" 白名单
(改动需配 golden set 回归测试)。

---

## 一、07-31 白天覆盖率(存档)

| 指标 | 数值 |
|---|---|
| 覆盖率 | 163/229 (71.2%) |
| 本轮启动前 | 161/229 (70.3%) |
| 本轮净增 | +2 |
| 累计(与最初 96/229 比) | +67 |

### 按经济体
| 经济体 | 覆盖 |
|---|---|
| CHN 中国 | 26/36 |
| IND 印度 | 24/36 |
| IDN 印尼 | 36/47 |
| LAO 老挝 | 18/27 |
| MNG 蒙古 | 17/21 |
| RUS 俄罗斯 | 20/34 |
| THA 泰国 | 22/28 |

### 按缺口根因
| 根因 | 数量 | 含义 |
|---|---|---|
| CORPUS_QUALITY | 15 | 有文本但只是摘要/stub,需重抓全文 |
| FETCH_GAP | 14 | 完全无本地文本,需抓取文档 |
| EXTRACTION | 37 | 有完整法规但未提取出条文 |

---

## 二、本轮做了什么

### 1. 发现并修复「假 FETCH_GAP」根因(最大成果)

**根因**: `run_corpus` 用 `law_name` **精确字符串匹配** 关联 inventory 与 manifest。
但 inventory 里的 `law_name` 常常是 `;\n\n` 拼接的多个法规名、或措辞与 manifest 不一致,
导致**文本明明在本地,却被判为"无文本"→ FETCH_GAP**,从未被提取。

**量化影响**: 68 个缺口中 **53 个**其实是文本已存在、仅名字不匹配的假缺口。

**修复**: `ai-service/submission/pipeline.py`
- 增加 `normalize_law_name` 归一化索引(去括号/年份/大小写)
- `law_name` 精确匹配失败时,按 `;`/换行拆分后逐段归一化匹配
- 文本读取同样走宽松解析路径

**收益**: 解锁了 CHN P10/P12、IND P3/P6/P7/P8/P10/P12、LAO P8/P12、RUS P12 的更多文本提取。

### 2. 抓取新法规文本(修复 2 个真 FETCH_GAP)

| 文件 | 来源 | 覆盖指标 | 状态 |
|---|---|---|---|
| `RUS/federal-law-no-161-fz-on-the-national-payment-system.txt` (24,038 chars, 俄语) | base.garant.ru | RUS 12.4.4, 12.4.7 | 已加入 manifest,提取成功 |
| `LAO/...31-na...pdf` (老挝语扫描件) | laotradeportal.gov.la | LAO 8.1 | **扫描件,OCR 失败**(老挝语 tesseract 不支持) |

### 3. 增量重跑验证

串行重跑有增益的 pillar(qwen2.5:14b, OLLAMA_CONTEXT_LENGTH=32768):

| 经济体 | Pillar | 结果 | 新增覆盖 |
|---|---|---|---|
| India | P8 | 4 provisions (P8-I4) | — |
| India | P10 | 2 provisions (P10-I2) | — |
| Russian Federation | P12 | 4 provisions (含 161-FZ) | **+1** (RUS 19→20) |
| China | P12 | 7 provisions (含 P12-I4.4 ×3) | **+1** (CHN 25→26) |
| Lao PDR | P8/P12 | P8 0 provisions | 未跑完 |

---

## 三、关键文件变更

| 文件 | 变更 |
|---|---|
| `ai-service/submission/pipeline.py` | `run_corpus` 增加归一化宽松匹配(假 FETCH_GAP 修复) |
| `data/round2_corpus/manifest.jsonl` | 521 行;RUS 12.4.4/12.4.7 指向新抓的干净 161-FZ 文本 |
| `data/round2_corpus/RUS/federal-law-no-161-fz-on-the-national-payment-system.txt` | 新抓取(替换旧的含 CSS 垃圾的文本) |
| `outputs/China_P12_20260731T132028.csv` | 新增,含 12.4.4 |
| `outputs/Russian_Federation_P12_20260731T121549.csv` | 新增,含 12.4.4/12.4.7 |
| `docs/round2_gap_worklist.csv` | 68 缺口工作清单 |

---

## 四、上次批量运行回顾(2026-07-28 22:14 → 07-30 16:13)

全 7 经济体用 `--from-corpus --provider ollama` 重跑,产出:

| 经济体 | provisions |
|---|---|
| China | 99 |
| India | 54 |
| Indonesia | 68 |
| Lao PDR | 22 |
| Mongolia | 39 |
| Russian Federation | 24 |
| Thailand | 70 |

**结论**: 优化上下文长度(32768)后 qwen 提取**没有新增任何单元格**——qwen2.5:14b 的提取能力就是当前覆盖的瓶颈,DeepSeek 已耗尽预算(300 RMB)。

---

## 五、剩余 66 个缺口怎么补

### A. 真 FETCH_GAP (14) — 需要抓文本
已全部测试过 URL,多数被 DNS/JS 墙拦截:
- gov.cn / mofcom.gov.cn(China): URL 404 或超时
- laoofficialgazette.gov.la、bol.gov.la(老挝): 403 / 扫描件
- nbtc.go.th(泰国): 超时
- 少数可从 Wayback Machine / 第三方镜像抓

### B. CORPUS_QUALITY (15) — 文本太短/非 statute
- 中文法规用「第X条」编号,分类器不识别为 STATUTE(已知问题)
- 部分确实只是公告/政策摘要(如 CHN 5.7 机构改革方案 1691 chars)

### C. EXTRACTION (37) — 提取召回瓶颈(最难)
- qwen2.5:14b 对非英文、复杂法律条文提取质量差
- IND P10 提取出 10.2 而非目标 10.3,说明指标分类不准
- 需要更强模型(DeepSeek 已无预算)

---

## 六、下一步建议

1. **等 DeepSeek 预算恢复或换更强本地模型**(如 qwen2.5:32b)再打 EXTRACTION
2. **改进分类器**识别中文「第X条」编号,把 CHN CORPUS_QUALITY 转成可提取
3. **OCR 老挝网安法/电子交易法**(需安装老挝语 tesseract 或付费 OCR)
4. 最后提交时用**所有时间戳 CSV 的并集**(coverage_report 已是并集逻辑)

---

## 附:验证命令

```bash
# 覆盖率
python tools/coverage_report.py outputs/ --gaps

# 输出缺口工作清单
python tools/coverage_report.py outputs/ --worklist docs/round2_gap_worklist.csv

# 单元测试
cd ai-service && python3 -m pytest tests/test_round2_methodology.py tests/test_coverage_report.py -x
```
