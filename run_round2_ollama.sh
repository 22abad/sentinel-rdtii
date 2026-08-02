#!/usr/bin/env bash
set -euo pipefail
# Full Round 2 submission on local Ollama — 7 economies × 12 pillars
# Runs 2 economies in parallel to maximize Ollama throughput
# Run:  bash run_round2_ollama.sh
# Time: ~5-9 hours (qwen2.5:14b, key-free)
# Output: outputs/<Economy>_P1-12_<timestamp>.csv + .json

echo "=============================================="
echo "SENTINEL Round 2 — full submission (Ollama)"
echo "Economies: CHN, IND, IDN, LAO, MNG, RUS, THA"
echo "Pillars:   1-12 (all)"
echo "Provider:  ollama (qwen2.5:14b, key-free)"
echo "Corpus:    data/round2_corpus (offline)"
echo "Parallel:  2 at a time"
echo "=============================================="
echo ""

# Detect already-completed economies
ALREADY_DONE=$(ls outputs/*_P1-2-3-4-5-6-7-8-9-10-11-12_*.csv 2>/dev/null | sed 's/.*\///' | sed 's/_.*//' | tr '\n' '|')
echo "Already completed: ${ALREADY_DONE:-none}"

ECONOMIES=(
  "China"
  "India"
  "Indonesia"
  "Lao PDR"
  "Mongolia"
  "Russian Federation"
  "Thailand"
)

START_AT=$(date +%s)

# Filter to only remaining economies
REMAINING=()
for e in "${ECONOMIES[@]}"; do
  KEY=$(echo "$e" | sed 's/ .*//')
  if ! echo "$ALREADY_DONE" | grep -qi "$KEY"; then
    REMAINING+=("$e")
  fi
done

echo "Remaining: ${REMAINING[*]}"
echo ""

# Process batches of 2
BATCH_SIZE=2
for ((i=0; i<${#REMAINING[@]}; i+=BATCH_SIZE)); do
  BATCH=("${REMAINING[@]:i:BATCH_SIZE}")
  echo "[$((i/BATCH_SIZE+1))] === Parallel batch: ${BATCH[*]} ==="
  echo "Started: $(date)"

  PIDS=()
  for ECON in "${BATCH[@]}"; do
    echo "  Starting: $ECON"
    python batch_run.py \
      --economies "$ECON" \
      --pillar all \
      --from-corpus \
      --provider ollama \
      --output-dir outputs &
    PIDS+=($!)
  done

  # Wait for all in this batch to finish
  for PID in "${PIDS[@]}"; do
    wait "$PID"
  done
  echo "Finished batch: $(date)"
  echo ""
done

ELAPSED=$(( $(date +%s) - START_AT ))
echo "=============================================="
echo "Done — all economies processed"
echo "Elapsed: $((ELAPSED / 3600))h $(( (ELAPSED % 3600) / 60 ))m"
echo "Outputs: outputs/"
echo "Run coverage: python tools/coverage_report.py outputs/ --gaps"
echo "=============================================="
