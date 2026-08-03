#!/bin/bash
# Fleet rerun after the 2026-08-03 extraction fixes (CJK reflow, isupper guard,
# catalogue rules). Gap pillars per economy from the 53-cell census.
cd /Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private
LOG=logs/fleet_20260803.log
echo "=== FLEET $(date) ===" >> $LOG
run() {
  echo "--- $1 pillars $2 $(date) ---" >> $LOG
  python3 main.py --economy "$1" --pillar "$2" --from-corpus --provider deepseek >> $LOG 2>&1
}
run China               "5,10,12"
run Indonesia           "2,3,4,5,7,8,10,11,12"
run India               "3,5,8,9,10,12"
run "Lao PDR"           "4,5,7,8,12"
run Mongolia            "5,8,11"
run "Russian Federation" "1,4,5,6,7,8,9,10,12"
run Thailand            "5,11,12"
echo "FLEET DONE $(date)" >> $LOG
