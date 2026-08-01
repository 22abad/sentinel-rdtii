#!/bin/bash
# Post-batch check: compare coverage before/after, print summary
set -euo pipefail
cd /Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private

LOGFILE="logs/post_batch_$(date +%Y%m%d_%H%M).log"
echo "=== Coverage check: $(date) ===" | tee "$LOGFILE"

# Run coverage report
python tools/coverage_report.py outputs/ --gaps 2>&1 | tee -a "$LOGFILE"

# List newest output files
echo "" | tee -a "$LOGFILE"
echo "=== Newest output files ===" | tee -a "$LOGFILE"
for eco in China India Indonesia "Lao PDR" Mongolia "Russian Federation" Thailand; do
    short=$(echo "$eco" | sed 's/ .*//;s/ .*//')
    newest=$(ls -t outputs/*${short}*.csv 2>/dev/null | head -1)
    if [ -n "$newest" ]; then
        rows=$(wc -l < "$newest")
        mtime=$(stat -f "%Sm" -t "%m-%d %H:%M" "$newest")
        echo "  $eco: $newest ($rows rows, $mtime)" | tee -a "$LOGFILE"
    fi
done

echo "" | tee -a "$LOGFILE"
echo "=== Coverage history ===" | tee -a "$LOGFILE"
if [ -f logs/coverage_timeline.csv ]; then
    cat logs/coverage_timeline.csv | tee -a "$LOGFILE"
fi

echo "" | tee -a "$LOGFILE"
echo "Log saved to: $LOGFILE"
