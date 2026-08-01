#!/bin/bash
# Morning report: check coverage, compare with baseline, list new files
set -euo pipefail
cd /Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private

echo "=========================================="
echo "  MORNING COVERAGE REPORT"
echo "  $(date)"
echo "=========================================="

echo ""
echo "=== Coverage Summary ==="
python tools/coverage_report.py outputs/ --gaps 2>&1

echo ""
echo "=== New Output Files (since 22:00 last night) ==="
find outputs/ -name "*.csv" -newer logs/batch_overnight.log -ls 2>/dev/null | awk '{print $NF, $6, $7, $8}' | sort

echo ""
echo "=== Batch Run Status ==="
if pgrep -f "main.py --economy" > /dev/null 2>&1; then
    echo "Batch run still active: $(ps aux | grep 'main.py' | grep -v grep)"
else
    echo "Batch run completed or not running"
fi

echo ""
echo "=== Manifest Stats ==="
wc -l data/round2_corpus/manifest.jsonl
echo "entries in manifest"

echo ""
echo "=== Ollama Status ==="
curl -s http://localhost:11434/api/tags | python3 -c "
import sys, json
d = json.load(sys.stdin)
for m in d.get('models', []):
    print(f\"  {m['name']}\")
" 2>/dev/null || echo "  Ollama not responding"

echo ""
echo "=========================================="
echo "  Check detailed gaps:"
echo "  python tools/coverage_report.py outputs/ --gaps"
echo "=========================================="
