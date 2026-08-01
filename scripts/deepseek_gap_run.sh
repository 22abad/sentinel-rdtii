#!/bin/bash
# DeepSeek flash gap-run — EXTRACTION 缺口 pillar (7 经济体, 只跑有缺口的)
# 2026-07-31 night plan (docs/tonight-plan-20260801.md)
set -u
cd /Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private

LOGDIR=logs
mkdir -p "$LOGDIR"
STAMP=$(date +%Y%m%dT%H%M)

# 经济体|pillar 组合 (来自 gap_worklist EXTRACTION)
declare -a RUNS=(
  "China|5,7,12"
  "Indonesia|2,3,4,5,8,10,11,12"
  "India|1,3,5,9,10,12"
  "Lao PDR|4,5,7,8,12"
  "Mongolia|8"
  "Russian Federation|1,5,7,9,10,11,12"
  "Thailand|11,12"
)

for r in "${RUNS[@]}"; do
  eco="${r%%|*}"; pillars="${r##*|}"
  echo "=== $eco (pillar $pillars) @ $(date '+%H:%M:%S') ===" | tee -a "$LOGDIR/deepseek_gap_$STAMP.log"
  python3 main.py --economy "$eco" --from-corpus --pillar "$pillars" --provider deepseek >> "$LOGDIR/deepseek_gap_$STAMP.log" 2>&1
  echo "   exit=$? @ $(date '+%H:%M:%S')" | tee -a "$LOGDIR/deepseek_gap_$STAMP.log"
done

echo "=== DONE @ $(date '+%H:%M:%S') ===" | tee -a "$LOGDIR/deepseek_gap_$STAMP.log"
