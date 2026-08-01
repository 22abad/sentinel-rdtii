#!/bin/bash
# Overnight runner: Fix corpus → Run qwen mapping → Loop until 08:30
# No DeepSeek API, no external costs.

WORKDIR="/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private"
cd "$WORKDIR" || exit 1

END_TIME="08:30"
LOGFILE="$WORKDIR/logs/overnight_run.log"
CORPUS_DIR="$WORKDIR/data/round2_corpus"
MANIFEST="$CORPUS_DIR/manifest.jsonl"
INVENTORY="$WORKDIR/data/round2_inventory.jsonl"
OUTPUT_DIR="$WORKDIR/outputs"

mkdir -p logs "$OUTPUT_DIR"

log() {
    echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOGFILE"
}

log "=== OVERNIGHT RUNNER STARTED ==="
log "Target: $END_TIME"
log "Qwen model with OLLAMA_CONTEXT_LENGTH=32768"

# Step 1: Clean HTML-wrapped corpus files
clean_corpus() {
    log "=== Step 1: Cleaning corpus files ==="
    python3 -c "
import os, re
from html.parser import HTMLParser

class Cleaner(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip_tags = {'script','style','noscript'}
        self.in_skip = False
    def handle_data(self, data):
        if not self.in_skip:
            t = data.strip()
            if t: self.text.append(t)
    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags: self.in_skip = True
    def handle_endtag(self, tag):
        if tag in self.skip_tags: self.in_skip = False

corpus_dir = '$CORPUS_DIR'
fixed = 0
for root, dirs, files in os.walk(corpus_dir):
    for fname in files:
        if not fname.endswith('.txt'): continue
        fpath = os.path.join(root, fname)
        data = open(fpath, 'rb').read()
        # Check if it's HTML
        head = data[:500].lower()
        if b'<html' not in head and b'<!doctype' not in head:
            continue
        # Extract text
        for enc in ['utf-8', 'gb18030', 'gbk', 'gb2312', 'iso-8859-1']:
            try:
                html = data.decode(enc)
                break
            except: continue
        else:
            html = data.decode('utf-8', errors='replace')
        
        c = Cleaner()
        c.feed(html)
        text = '\n'.join(c.text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        if len(text) > 500:
            open(fpath, 'w', encoding='utf-8').write(text)
            fixed += 1
            print(f'  Cleaned {fname}: {len(text)} chars')
print(f'Fixed {fixed} HTML-wrapped files')
" 2>&1 | tee -a "$LOGFILE"
}

# Step 2: Update manifest - deduplicate and add missing entries
update_manifest() {
    log "=== Step 2: Updating manifest ==="
    python3 -c "
import json, os, re, hashlib

corpus_dir = '$CORPUS_DIR'
manifest = '$MANIFEST'
inventory = '$INVENTORY'

# Load existing manifest
entries = {}
if os.path.exists(manifest):
    with open(manifest) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', line)
            try:
                d = json.loads(clean)
                key = (d.get('economy',''), d.get('indicator_id',''), d.get('law_name','')[:80])
                # Keep larger version
                if key not in entries or d.get('char_count',0) > entries[key].get('char_count',0):
                    entries[key] = d
            except: pass

# Find text files not in manifest
for root, dirs, files in os.walk(corpus_dir):
    for fname in files:
        if not fname.endswith('.txt'): continue
        fpath = os.path.join(root, fname)
        # Look up by filename in existing entries
        found = False
        rel = os.path.relpath(fpath, corpus_dir)
        for key, d in list(entries.items()):
            tp = d.get('text_path','')
            if rel in tp or fname in tp:
                found = True
                break
        if not found:
            # Auto-add missing entry
            chars = os.path.getsize(fpath)
            sha = hashlib.sha256(open(fpath,'rb').read()).hexdigest()
            eco = os.path.basename(root)
            entry = {
                'economy': eco,
                'law_name': fname.replace('.txt','').replace('-',' ').title(),
                'indicator_id': 'auto',
                'urls': [],
                'text_path': f'data/round2_corpus/{eco}/{fname}',
                'status': 'ok',
                'char_count': chars,
                'sha256': sha
            }
            key = (eco, 'auto', entry['law_name'][:80])
            entries[key] = entry
            print(f'  Added auto entry for {eco}/{fname} ({chars} chars)')

# Save deduplicated manifest
with open(manifest, 'w') as f:
    for d in entries.values():
        f.write(json.dumps(d, ensure_ascii=False) + '\n')
print(f'Manifest: {len(entries)} unique entries')
" 2>&1 | tee -a "$LOGFILE"
}

# Step 3: Run qwen mapping for one economy
run_mapping() {
    local econ=$1
    local round_num=$2
    log "=== Step 3: qwen mapping for $econ (round $round_num) ==="
    
    python3 -c "
import sys
sys.path.insert(0, '$WORKDIR')
from ai_service.mapping_pipeline import MappingPipeline
import asyncio

async def run():
    pipe = MappingPipeline(economy='$econ')
    # Use qwen2.5:14b with OLLAMA_CONTEXT_LENGTH=32768
    pipe.model = 'qwen2.5:14b'
    pipe.context_length = 32768
    pipe.run_name = f'overnight_round{round_num}_{econ}'
    
    result = await pipe.run()
    print(f'Results: {result}')
    return result

asyncio.run(run())
" 2>&1 | tee -a "$LOGFILE"
    
    log "$econ round $round_num complete"
}

# Step 4: Check coverage
check_coverage() {
    log "=== Step 4: Coverage check ==="
    python3 -c "
import json, os, csv, glob
from collections import defaultdict

eco_map = {'China':'CHN','India':'IND','Indonesia':'IDN','Lao PDR':'LAO','Mongolia':'MNG','Russian Federation':'RUS','Thailand':'THA'}
inventory = {}
with open('$INVENTORY') as f:
    for line in f:
        inv = json.loads(line)
        score = float(inv.get('official_score', 0))
        if score > 0:
            code = eco_map.get(inv['economy'].strip(), inv['economy'].upper())
            key = (code, inv['indicator_id'])
            if key not in inventory:
                inventory[key] = inv

covered = set()
for fpath in sorted(glob.glob('$OUTPUT_DIR/*.csv')):
    with open(fpath) as f:
        reader = csv.DictReader(f)
        for row in reader:
            e = row.get('Economy','').strip()
            ind = row.get('Indicator ID','').strip()
            if e and ind:
                covered.add((e, ind))

total = len(inventory)
total_covered = len(covered & set(inventory.keys()))
pct = round(100 * total_covered / total, 1) if total else 0
print(f'Coverage: {total_covered}/{total} ({pct}%)')
print(f'Total output files: {len(glob.glob(\"$OUTPUT_DIR/*.csv\"))}')
" 2>&1 | tee -a "$LOGFILE"
}

# Main loop
round_num=0
while true; do
    round_num=$((round_num + 1))
    log ""
    log "=== LOOP ROUND $round_num ==="
    log "Current time: $(date '+%H:%M')"
    
    # Stop at 08:30
    if [[ "$(date '+%H:%M')" > "$END_TIME" ]] || [[ "$(date '+%H:%M')" == "$END_TIME" ]]; then
        log "Reached $END_TIME, stopping"
        break
    fi
    
    clean_corpus
    update_manifest
    
    # Run for each economy that hasn't been mapped with improved corpus
    for econ in CHN IND IDN LAO MNG RUS THA; do
        # Check if we're past end time
        if [[ "$(date '+%H:%M')" > "$END_TIME" ]]; then
            log "Reached $END_TIME mid-loop, stopping"
            break 2
        fi
        
        # Only run if no recent output exists (within last 2 hours)
        latest_csv=$(ls -t "$OUTPUT_DIR"/*"$econ"*".csv" 2>/dev/null | head -1)
        if [ -n "$latest_csv" ]; then
            age_mins=$(( ($(date +%s) - $(stat -f %m "$latest_csv")) / 60 ))
            if [ "$age_mins" -lt 120 ]; then
                log "Skipping $econ - recent output exists (${age_mins}m ago)"
                continue
            fi
        fi
        
        run_mapping "$econ" "$round_num"
        
        # Brief pause between economies
        sleep 5
    done
    
    check_coverage
    
    # Brief pause before next round
    log "Round $round_num complete, sleeping 60s before next round"
    sleep 60
done

log "=== OVERNIGHT RUNNER FINISHED ==="
check_coverage
log "Final coverage report above"
