# Agent preferences — for opencode sessions

## Behavior
- **不要问,直接干.** Execute next steps without asking for permission. Only ask if truly blocked or ambiguous.
- Be concise, reply in Chinese when user writes in Chinese.
- Run verification (coverage report, smoke test) automatically after any change.
- All times are Asia/Shanghai (UTC+8) unless noted.

## How to check results

### 实时监控跑批
```bash
# 看最新输出
tail -f outputs/log_<Economy>.txt

# 看最终 CSV 行数
wc -l outputs/<Economy>_P*.csv
```

### 覆盖率检查
```bash
python tools/coverage_report.py --gaps
```

### 查看最终产出
```bash
# 列出所有输出文件
ls -lh outputs/*.csv outputs/*.json

# 看某经济体具体条目
python tools/coverage_report.py outputs/ --economy Thailand
```

### 测试
```bash
pytest tests/ -x          # 跑全部
pytest tests/ -k thailand  # 跑特定经济体
```

## Autonomous workflow (不要问,直接干)

### Priority order
1. **FETCH_GAP** → 21 cells — find alternative URL / download law text, add to corpus + manifest
2. **CORPUS_QUALITY** → 18 cells — verify text is correct (right law, right content, sufficient length)
3. **EXTRACTION** → 94 cells — debug why provisions aren't surfacing; adjust extraction gates, re-run mapping
4. After each fix batch → run `python tools/coverage_report.py --gaps` and update `docs/round2_gap_worklist.csv`
5. Re-run mapping for affected economy: `python main.py --economy X --from-corpus --pillar all --provider ollama 2>&1 | tee -a outputs/log_X.txt`
6. After each full re-run → `pytest tests/ -x`

### FETCH_GAP workflow
1. Find law name in `data/round2_inventory.jsonl` (search by economy + indicator_id)
2. Try alternative official URLs from same law (look at other indicators referencing same law)
3. Try web search for the law text from official gov portal
4. Download text via `python -c "import requests; r = requests.get(url, timeout=60); print(r.text)"` or `wget`
5. Save to `data/round2_corpus/{ECO}/{law-slug}.txt`
6. Add entry to `data/round2_corpus/manifest.jsonl` with sha256 + char_count
7. Update gap_worklist.csv: remove FETCH_GAP row or reclassify

### EXTRACTION workflow
1. Check corpus text exists (`ls data/round2_corpus/{ECO}/`), verify quality
2. Check what indicator needs (read `requirements/Hackthon Knowledge Products/` methodology)
3. Debug extraction pipeline — is it chunking? classification? language issue?
4. Common gates that silently drop rows: is_section_header, weak-evidence (<45 chars), citation-style quote, no statute word, operative language, self-title mismatch
5. Fix issue, re-run mapping for affected economy + pillar
6. Verify cell is now covered via coverage_report.py

### When to switch tasks
- If FETCH_GAP URLs are truly dead with no alternative, move to next cell
- After all FETCH_GAP attempted → move to CORPUS_QUALITY
- After CORPUS_QUALITY → move to EXTRACTION
- If stuck on a cell > 15 min, skip and come back
- After a full re-run cycle, re-assess coverage and decide next priority
- Don't ask for permission — just do it and report what happened

## Current memory

### 当前状态 (2026-07-25 15:30 CST)
- **Round 2 pipeline**: CHN + IND 正在跑（pipeline_watcher 自动排队 IDN→LAO→MNG→RUS→THA）
- **覆盖率**: 96/229 (41.9%)，预计 CHN/IND 重跑后提升
- **EXTRACTION gap fix round 1 已完成**:
  - `classifier.py`: 新增 36 个 missing indicator 的多语言关键词（中文、印尼语、俄语、泰语）
  - `eligibility.py`: 8 个 P6/P7 regex pattern 新增俄语/印尼语/泰语关键词，覆盖~15 个 eligibility 门控 gap
  - 预计解锁 ~80/100 EXTRACTION gaps。剩余主要在 LAO、MNG（语种复杂，LLM 能力瓶颈）
- **Ollama**: qwen2.5:14b on Metal (M5 Pro, 48GB), `-np 2`

### 已知问题
1. qwen2.5:14b every call has ~19.5s hidden overhead with `-np 1`; `-np 2` + 并行双进程解决
2. Metal GPU 正常工作 (ggml_metal_init confirmed)
3. LAO + MNG 语种超出 qwen2.5:14b 能力范围，需更强模型
4. `--pillar all` 死掉通常因为有残留进程抢 Ollama 槽; 先 `pkill -f batch_run` 再启动

### 后续计划
1. 等 CHN + IND 跑完 → pipeline 自动启动 IDN 等
2. 全部重跑完后 → `python tools/coverage_report.py outputs/ --gaps` 看效果
3. 剩余 LAO/MNG ~15 cells 需要更强模型（DeepSeek 或更高参数本地模型）
4. 考虑把 `run_round2_ollama.sh` 改为直接用 `pipeline_watcher.sh`
