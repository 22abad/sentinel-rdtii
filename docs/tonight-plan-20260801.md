# 过夜工作计划 — 7/31 22:00 → 8/1 12:00 (系统时区 +1)

目标:Round 2 覆盖率 71.2% (163/229) → 争取 170+;所有产出提交推送;vault 记录。
Dong 2026-07-31 22:10 更新:DeepSeek 300 RMB 还剩 ~200,用 flash;qwen 不跑全量只抽样;早结束早收尾。

## 缺口现状 (docs/round2_gap_worklist.csv, 66 个)

- EXTRACTION 41 (有文本提取不出) → **DeepSeek flash 打**,按 (economy, pillar) 组合只跑缺口的
- CORPUS_QUALITY 17 (文本太短/非 statute) → auto_fix_corpus.py 重抓
- FETCH_GAP 8 (完全无文本) → auto_fix_corpus.py Wayback/直抓

## 执行主线 (并行)

| 线 | 内容 | 预算 |
|---|---|---|
| A | auto_fix_corpus.py 后台 (FETCH_GAP 8 + CORPUS_QUALITY 17) | $0 |
| B | DeepSeek flash 增量跑 EXTRACTION 缺口 pillar (7 经济体) | ~$10-13 (~90 RMB) |
| C | 抓完新文本 → 补跑对应 pillar | $0-2 |

DeepSeek 跑批组合:
- CHN: pillar 5,7,12
- IDN: pillar 2,3,4,5,8,10,11,12
- IND: pillar 1,3,5,9,10,12
- LAO: pillar 4,5,7,8,12
- MNG: pillar 8
- RUS: pillar 1,5,7,9,10,11,12
- THA: pillar 11,12

跳过:中文「第X条」分类器代码改动 (DeepSeek 对中文提取更强,风险>收益);qwen 32b 抽样 (DeepSeek 质量更好)。

## 阶段 C (收尾,早结束早收尾)

| # | 事项 | 验收 |
|---|---|---|
| C1 | merge_submission 并入所有新输出 | 官方格式 CSV/JSON |
| C2 | coverage_report 验证覆盖率 | 期望 163 → 170+ |
| C3 | pytest 全绿 | 不绿不提交 |
| C4 | 提交 + 推送 + engineering log | PR 或直接 push |
| C5 | 写 Obsidian vault (结果 + problem→fix 故事) | vault 有记录 |
| C6 | 更新 sprint summary / meeting report | 数字可复现 |

## 风险与对策

- LAO 上次卡死 → 已重启 + 监控;若再卡,记录卡点文档,跳过。
- DeepSeek 预算耗尽 → 每轮跑完查余额;不够就本地 qwen 14b 兜底。
- 老挝语扫描件 OCR 不支持 → 跳过,不浪费时间。

## 明天 12:00 后

- 8/2 pitch deck 团队评审 → 准备终版 (今天已撤回草稿)。
