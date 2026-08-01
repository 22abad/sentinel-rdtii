#!/bin/bash
# Auto overnight: fix corpus → run qwen mapping → loop until 08:30
# Usage:  bash scripts/auto_overnight.sh [end_time]
# Default end time: 08:30 (uses 24h format)

set -euo pipefail

WORKDIR="/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private"
cd "$WORKDIR"

END_TIME="${1:-08:30}"
LOGFILE="$WORKDIR/logs/overnight_$(date +%Y%m%d).log"
mkdir -p logs

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOGFILE"; }

# Check if current time has passed end_time (handles overnight, e.g. 22:00 → 08:30)
past_end() {
    local now_h=$(date '+%H')
    local now_m=$(date '+%M')
    local end_h="${END_TIME%%:*}"
    local end_m="${END_TIME##*:}"
    # Strip leading zeros
    now_h=$((10#$now_h)); now_m=$((10#$now_m))
    end_h=$((10#$end_h)); end_m=$((10#$end_m))
    local now_min=$((now_h * 60 + now_m))
    local end_min=$((end_h * 60 + end_m))
    # If end < now and we haven't crossed midnight logic
    # If end is in the morning (0-12) and now is evening (13-23), we haven't reached it yet
    if [ $end_min -lt 720 ] && [ $now_min -ge 720 ]; then
        # End is morning (before noon) and now is afternoon/evening → haven't reached it
        return 1  # false
    fi
    # Normal comparison (same day or both in morning)
    [ $now_min -ge $end_min ]
}

# ─── Step 1: Fix manifest JSON encoding issues ───
fix_manifest() {
    log "=== Fix manifest encoding ==="
    python3 -c "
import json, re
manifest = '$WORKDIR/data/round2_corpus/manifest.jsonl'
entries = []
with open(manifest) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', line)
        try:
            d = json.loads(clean)
            entries.append(d)
        except:
            pass
with open(manifest, 'w') as f:
    for e in entries:
        f.write(json.dumps(e, ensure_ascii=False) + '\n')
print(f'Fixed manifest: {len(entries)} entries')
" 2>&1 | tee -a "$LOGFILE"
}

# ─── Step 2: Clean HTML-wrapped corpus files ───
clean_corpus() {
    log "=== Clean HTML corpus ==="
    python3 -c "
import os, re
from html.parser import HTMLParser

class HTMLExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip = {'script','style','noscript'}
        self.in_skip = False
    def handle_data(self, data):
        if not self.in_skip:
            t = data.strip()
            if t: self.text.append(t)
    def handle_starttag(self, tag, attrs):
        if tag in self.skip: self.in_skip = True
    def handle_endtag(self, tag):
        if tag in self.skip: self.in_skip = False

corpus_dir = '$WORKDIR/data/round2_corpus'
fixed = 0
for root, dirs, files in os.walk(corpus_dir):
    for fname in files:
        if not fname.endswith('.txt'): continue
        fpath = os.path.join(root, fname)
        data = open(fpath, 'rb').read()
        if b'<html' not in data[:500].lower() and b'<!doctype' not in data[:500].lower():
            continue
        for enc in ['utf-8','gb18030','gbk','gb2312','iso-8859-1']:
            try:
                html = data.decode(enc); break
            except: continue
        else:
            html = data.decode('utf-8', errors='replace')
        ex = HTMLExtractor()
        ex.feed(html)
        text = '\n'.join(ex.text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        if len(text) > 200:
            open(fpath, 'w', encoding='utf-8').write(text)
            fixed += 1
            print(f'  Cleaned: {fname} → {len(text)} chars')
print(f'Fixed {fixed} HTML files')
" 2>&1 | tee -a "$LOGFILE"
}

# ─── Step 3: Fetch missing texts via alternative URLs ───
fetch_missing() {
    log "=== Fetch missing texts ==="
    python3 -c "
import json, re, os, urllib.request, ssl, time, hashlib

ssl_ctx = ssl._create_unverified_context()
corpus_dir = '$WORKDIR/data/round2_corpus'
manifest_path = '$WORKDIR/data/round2_corpus/manifest.jsonl'
inventory_path = '$WORKDIR/data/round2_inventory.jsonl'

# Load manifest
manifest = {}
with open(manifest_path) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', line)
        try:
            d = json.loads(clean)
            manifest[(d.get('economy',''), d.get('indicator_id',''))] = d
        except: pass

# Load inventory
eco_map = {'China':'CHN','India':'IND','Indonesia':'IDN','Lao PDR':'LAO','Mongolia':'MNG','Russian Federation':'RUS','Thailand':'THA'}
inv_cells = {}
with open(inventory_path) as f:
    for line in f:
        inv = json.loads(line)
        if float(inv.get('official_score',0)) <= 0: continue
        code = eco_map.get(inv['economy'].strip(), inv['economy'].upper())
        key = (code, inv['indicator_id'])
        if key not in inv_cells:
            inv_cells[key] = inv

# Try to fetch from each law's URL
fetched = 0
for (eco, ind), inv in sorted(inv_cells.items()):
    key = (eco, ind)
    if key in manifest:
        continue  # Already has entry
    
    law_name = inv.get('law_name','') or ''
    urls = inv.get('urls', [])
    if not urls:
        # Try source field
        src = inv.get('source','')
        if src: urls = [src]
    if not urls:
        continue
    
    print(f'  Missing: {eco} {ind} — {law_name[:50]}')
    for url in urls[:3]:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=10, context=ssl_ctx)
            content = resp.read()
            text = content.decode('utf-8', errors='replace')
            if len(text) < 200:
                continue
            
            # Save file
            slug = re.sub(r'[^a-z0-9]+', '-', law_name.lower())[:60].strip('-')
            fname = f'{slug}.txt' if slug else f'{eco.lower()}-{ind}.txt'
            eco_dir = os.path.join(corpus_dir, eco)
            os.makedirs(eco_dir, exist_ok=True)
            fpath = os.path.join(eco_dir, fname)
            open(fpath, 'w', encoding='utf-8').write(text)
            
            # Add manifest entry
            entry = {
                'economy': eco, 'law_name': law_name, 'indicator_id': ind,
                'urls': [url], 'text_path': f'data/round2_corpus/{eco}/{fname}',
                'status': 'ok', 'char_count': len(text),
                'sha256': hashlib.sha256(text.encode()).hexdigest()
            }
            with open(manifest_path, 'a') as mf:
                mf.write(json.dumps(entry, ensure_ascii=False) + '\n')
            
            print(f'    Fetched {len(text)} chars from {url[:60]}')
            fetched += 1
            break
        except Exception as e:
            print(f'    Error: {e}')
            time.sleep(0.5)
            continue
    
    if fetched >= 10:
        break  # Limit per round

print(f'Fetched {fetched} new texts')
" 2>&1 | tee -a "$LOGFILE"
}

# ─── Step 4: Run qwen mapping for a specific economy ───
run_mapping() {
    local economy="$1"
    local round_num="$2"
    log "=== Run qwen for $economy (round $round_num) ==="
    
    export OLLAMA_CONTEXT_LENGTH=32768
    export OLLAMA_MODEL=qwen2.5:14b
    
    python main.py \
        --economy "$economy" \
        --pillar all \
        --from-corpus \
        --provider ollama \
        --output-dir outputs \
        2>&1 | tee -a "$LOGFILE" "$WORKDIR/outputs/log_${economy}_round${round_num}.txt"
    
    log "$economy round $round_num complete"
}

# ─── Step 5: Check coverage ───
check_coverage() {
    log "=== Coverage check ==="
    python3 "$WORKDIR/tools/coverage_report.py" "$WORKDIR/outputs/" --gaps 2>&1 | tee -a "$LOGFILE"
}

# ─── Main loop ───
COVERAGE_LOG="$WORKDIR/logs/coverage_timeline.csv"
if [ ! -f "$COVERAGE_LOG" ]; then
    echo "timestamp,total,covered,pct,fetch_gap,corpus_quality,extraction" > "$COVERAGE_LOG"
fi

log "=== OVERNIGHT RUNNER STARTED ==="
log "Target end time: $END_TIME"
log "Model: qwen2.5:14b with OLLAMA_CONTEXT_LENGTH=32768"
log "Log: $LOGFILE"

# Pre-flight fixes
fix_manifest
clean_corpus

# Run mapping for each economy once (this will take hours)
ECONOMIES=("China" "India" "Indonesia" "Lao PDR" "Mongolia" "Russian Federation" "Thailand")
ROUND=0

while true; do
    ROUND=$((ROUND + 1))
    log ""
    log "═══ ROUND $ROUND ═══"
    # Fetch missing texts
    fetch_missing
    check_coverage
    
    # Check if coverage recently improved; if stalled, try different approach
    # For now, just keep running through economies
    
    # Run mapping for each economy with 2-at-a-time parallelism
    log "Starting mapping runs..."
    
    BATCH_SIZE=2
    for ((i=0; i<${#ECONOMIES[@]}; i+=BATCH_SIZE)); do
        # Check end time in between batches
        if past_end; then
            log "Reached $END_TIME, stopping mid-batch"
            break 2
        fi
        
        BATCH=("${ECONOMIES[@]:i:BATCH_SIZE}")
        log "Batch: ${BATCH[*]}"
        
        PIDS=()
        for ECON in "${BATCH[@]}"; do
            # Skip if coverage improved enough or no time left
            run_mapping "$ECON" "$ROUND" &
            PIDS+=($!)
        done
        
        # Wait for this batch
        for PID in "${PIDS[@]}"; do
            wait "$PID"
        done
        log "Batch complete"
    done
    
    # Check coverage after full round
    check_coverage
    
    # Save coverage snapshot
    COV_LINE=$(grep -oP '\d+/\d+ \(\d+\.\d+%\)' "$LOGFILE" | tail -1)
    log "Round $ROUND coverage: $COV_LINE"
    
    # Brief pause before next round
    sleep 30
done

log "=== OVERNIGHT RUNNER FINISHED ==="
check_coverage
log "Final report above"

# Print summary
echo ""
echo "============================================"
echo "  OVERNIGHT RUN SUMMARY"
echo "============================================"
echo "  Ended at: $(date '+%Y-%m-%d %H:%M')"
echo "  Log: $LOGFILE"
echo "  Coverage: check $COVERAGE_LOG for timeline"
echo "============================================"
