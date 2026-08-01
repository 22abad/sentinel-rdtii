#!/bin/bash
# Monitor batch run progress
# Usage: bash scripts/monitor.sh
cd /Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private
LOGFILE="logs/batch_overnight.log"
echo "=== Monitor $(date) ==="
echo "PID: $(pgrep -f 'main.py --economy' | tr '\n' ' ')"
echo "Last 10 lines of log:"
tail -10 "$LOGFILE" 2>/dev/null
echo ""
echo "Output files modified today:"
find outputs/ -name "*.csv" -mtime -1 -ls 2>/dev/null | awk '{print $NF, $8, $9, $10}' | sort -k1
echo ""
echo "Ollama status:"
curl -s http://localhost:11434/api/tags | python3 -c "import sys,json; d=json.load(sys.stdin); [print(m['name'],m.get('details',{}).get('parameter_size','')) for m in d.get('models',[])]" 2>/dev/null || echo "  Ollama not responding"
