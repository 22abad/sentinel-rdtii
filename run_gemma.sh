#!/usr/bin/env bash
set -uo pipefail
# Run ALL economies with gemma4:12b, one at a time, log results
WORKDIR="/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private"
cd "$WORKDIR"

ECONOMIES=("Lao PDR" "China" "India" "Thailand" "Indonesia" "Mongolia" "Russian Federation")
START_AT=$(date +%s)

echo "=============================================="
echo "gemma4:12b re-run — all 7 economies"
echo "Started: $(date)"
echo "=============================================="
echo ""

for econ in "${ECONOMIES[@]}"; do
  key=$(echo "$econ" | sed 's/ .*//')
  echo "[$(date '+%H:%M:%S')] === Starting: $econ ==="
  
  OLLAMA_MODEL=gemma4:12b python batch_run.py \
    --economies "$econ" \
    --pillar all \
    --from-corpus \
    --provider ollama \
    --output-dir outputs \
    > "/tmp/${key}_gemma_out.txt" 2>"/tmp/${key}_gemma_err.txt"
  
  echo "[$(date '+%H:%M:%S')] === Done: $econ ==="
  
  # Coverage report
  python tools/coverage_report.py outputs/ --gaps 2>&1 | tee -a /tmp/gemma_progress.log
  
  # Record row count
  csv=$(ls -t outputs/${key}_P1-*.csv 2>/dev/null | head -1)
  if [ -n "$csv" ]; then
    rows=$(wc -l < "$csv")
    echo "[$(date '+%H:%M:%S')] $econ output: $csv ($rows rows)"
  fi
  
  echo "---" >> /tmp/gemma_progress.log
  echo ""
done

ELAPSED=$(( $(date +%s) - START_AT ))
echo "=============================================="
echo "ALL DONE — $(date)"
echo "Elapsed: $((ELAPSED / 3600))h $(( (ELAPSED % 3600) / 60 ))m"
echo "Final coverage:" >> /tmp/gemma_progress.log
python tools/coverage_report.py outputs/ --gaps 2>&1 | tail -15 >> /tmp/gemma_progress.log
echo "=============================================="
