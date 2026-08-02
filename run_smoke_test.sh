#!/usr/bin/env bash
set -euo pipefail
# Quick smoke test — one economy, one pillar (~5-15 min)
echo "=== Smoke test: Mongolia Pillar 6 (Cross-border Data Flows) ==="
echo "Started: $(date)"
python main.py --economy Mongolia --from-corpus --pillar 6 --provider ollama
echo "Finished: $(date)"
echo ""
echo "Check outputs/ for <Mongolia_P6_*.csv>"
echo "If this works, run: bash run_round2_ollama.sh"
