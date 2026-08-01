#!/bin/bash
# 过夜收尾:merge → coverage → TG 汇报 (2026-08-01 晨)
# 一次执行全部完成;幂等,可重复跑。
set -u
cd /Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private

echo "=== 1/3 merge ==="
python3 tools/merge_submission.py outputs outputs/round2_submission_merged 2>&1 | tail -8

echo "=== 2/3 coverage ==="
python3 tools/coverage_report.py outputs/ 2>&1 | head -8
python3 tools/coverage_report.py outputs/ --worklist docs/round2_gap_worklist.csv 2>&1 | tail -2

echo "=== 3/3 TG ==="
source /Users/dxz/.claude/jobs/51e8603f/tmp/tg.env
COV=$(python3 tools/coverage_report.py outputs/ 2>/dev/null | grep "Official scorable" | head -1)
ROWS=$(python3 -c "
import csv
n = sum(1 for _ in csv.DictReader(open('outputs/round2_submission_merged/all_economies_merged.csv')))
print(n)
" 2>/dev/null)
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d chat_id="${TELEGRAM_CHAT_ID}" \
  --data-urlencode text="🌅 过夜跑批收尾完成

✅ DeepSeek 7/7全绿: CHN57 IDN77 IND33 LAO31 MNG4 RUS18 THA22 = 242新provisions
✅ LAO qwen补跑+4 (昨天卡点已补)
✅ Wayback垃圾事故闭环: 0行污染
📊 ${COV}
📄 merged总行数: ${ROWS}

待办: pytest→提交推送→sprint文档更新" >/dev/null && echo "TG sent ✓" || echo "TG FAILED"
