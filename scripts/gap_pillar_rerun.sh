#!/bin/bash
# Gap pillar DeepSeek re-run — 5 economies, targeted pillars
set -u
cd /Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private
LOG="logs/hunt_gap_pillars_$(date +%Y%m%dT%H%M).log"

echo "=== Gap Pillar Re-run $(date) ===" | tee "$LOG"

run_eco() {
  local eco="$1" pillars="$2"
  echo "" | tee -a "$LOG"
  echo "=== $eco (pillar $pillars) @ $(date +%H:%M:%S) ===" | tee -a "$LOG"
  python3 main.py --economy "$eco" --from-corpus --pillar "$pillars" --provider deepseek >> "$LOG" 2>&1
  echo "   exit=$? @ $(date +%H:%M:%S)" | tee -a "$LOG"
}

run_eco "Indonesia" "2,3,4,5,7,8,10,11,12"
run_eco "Lao PDR" "4,5,7,8,12"
run_eco "Mongolia" "5,8,11"
run_eco "Russian Federation" "1,4,5,6,7,8,9,10,11,12"
run_eco "Thailand" "5,11,12"

echo "" | tee -a "$LOG"
echo "=== DONE $(date) ===" | tee -a "$LOG"
