#!/usr/bin/env python3
"""
Auto-fix corpus texts: Wayback Machine fetch + text quality improvement.
Runs until interrupted. Outputs a log of what was done.
"""
import json, os, sys, re, hashlib, time, urllib.request, urllib.error, ssl
from html.parser import HTMLParser
from urllib.parse import urlparse

WORKDIR = '/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private'
CORPUS_DIR = os.path.join(WORKDIR, 'data', 'round2_corpus')
MANIFEST = os.path.join(CORPUS_DIR, 'manifest.jsonl')
INVENTORY = os.path.join(WORKDIR, 'data', 'round2_inventory.jsonl')

# Wayback Machine CDX API
CDX_API = 'https://web.archive.org/cdx/search/cdx?url={url}&output=json&limit=5&fl=timestamp,original,statuscode'

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip_tags = {'script','style','noscript'}
        self.in_skip = False
    def handle_data(self, data):
        if not self.in_skip:
            t = data.strip()
            if t:
                self.text.append(t)
    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.in_skip = True
    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            self.in_skip = False

def extract_text(html_bytes):
    """Extract clean text from HTML, auto-detect encoding."""
    # Try multiple encodings
    for enc in ['utf-8', 'gb18030', 'gbk', 'gb2312', 'iso-8859-1']:
        try:
            html = html_bytes.decode(enc)
            break
        except:
            continue
    else:
        html = html_bytes.decode('utf-8', errors='replace')

    extractor = TextExtractor()
    extractor.feed(html)
    text = '\n'.join(extractor.text)
    # Remove repeated short lines (navigation debris)
    lines = [l for l in text.split('\n') if len(l.strip()) > 10 or not l.strip()]
    return '\n'.join(lines)

# SSL context for Wayback Machine (cert issues on macOS)
SSL_CTX = ssl._create_unverified_context()

GARBAGE_MARKERS = (
    'Keep the news in the Wayback Machine',
    'Internet Archive logo',
    'A line drawing of the Internet Archive headquarters',
)

def is_garbage_page(text):
    """The Wayback/Archive.org UI shell (not the archived document itself)."""
    head = text[:3000]
    return any(m in head for m in GARBAGE_MARKERS)

def wb_fetch(url, timeout=45):
    """Try to fetch a URL via Wayback Machine. Returns (text, timestamp) or (None, None)."""
    encoded = urllib.request.quote(url, safe='/:?=&#')
    # Step 1: use CDX to find latest snapshot
    cdx_url = CDX_API.format(url=encoded)
    try:
        req = urllib.request.Request(cdx_url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX)
        data = json.loads(resp.read().decode())
        if len(data) <= 1:
            return None, None
        snapshots = data[1:]
        # Prefer 200 responses, newest first
        snapshots.sort(key=lambda x: (x[2] == '200', x[0]), reverse=True)
        ts, orig_url, status = snapshots[0][0], snapshots[0][1], snapshots[0][2]
    except Exception as e:
        print(f"  CDX error: {e}")
        return None, None

    # Step 2: fetch raw content via multiple modes
    for mode in ['if_', 'id_', '']:
        raw_url = f'https://web.archive.org/web/{ts}{mode}{orig_url}'
        try:
            req = urllib.request.Request(raw_url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX)
            content = resp.read()
            # If it's HTML with Wayback banner, try next mode
            if mode == '' and (b'wayback' in content[:1000].lower() or b'banner' in content[:1000].lower()):
                continue
            if b'<html' in content[:500] or b'<!DOCTYPE' in content[:500]:
                text = extract_text(content)
            else:
                text = content.decode('utf-8', errors='replace')
            if is_garbage_page(text):
                print(f"    Rejected: Wayback UI shell, not the document")
                continue
            if len(text) > 200:
                return text, ts
        except:
            continue
    return None, None

def direct_fetch(url, timeout=30):
    """Try direct fetch of a URL."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX)
        content = resp.read()
        content_type = resp.headers.get('Content-Type', '')
        if 'pdf' in content_type:
            return None
        if b'<html' in content[:500] or b'<!DOCTYPE' in content[:500]:
            text = extract_text(content)
        else:
            text = content.decode('utf-8', errors='replace')
        return text
    except Exception as e:
        print(f"    Direct fetch error: {e}")
        return None

def load_manifest():
    """Load manifest, handling malformed JSON lines."""
    entries = []
    with open(MANIFEST) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            # Fix common control character issues
            clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', line)
            try:
                d = json.loads(clean)
                entries.append(d)
            except json.JSONDecodeError as e:
                print(f"  Warning: manifest line {i} invalid: {e}")
    return entries

def save_manifest(entries):
    """Save manifest with proper JSON lines."""
    with open(MANIFEST, 'w') as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')

def find_gap_cells(entries):
    """Identify cells needing better text: FETCH_GAP and CORPUS_QUALITY."""
    # Load inventory for indicator mapping
    eco_map = {'China':'CHN','India':'IND','Indonesia':'IDN','Lao PDR':'LAO','Mongolia':'MNG','Russian Federation':'RUS','Thailand':'THA'}
    inv_cells = {}
    with open(INVENTORY) as f:
        for line in f:
            inv = json.loads(line)
            score = float(inv.get('official_score', 0))
            if score <= 0:
                continue
            code = eco_map.get(inv['economy'].strip(), inv['economy'].upper())
            key = (code, inv['indicator_id'])
            if key not in inv_cells:
                inv_cells[key] = []
            inv_cells[key].append(inv)

    # Find cells that have inventory but no manifest entry (FETCH_GAP)
    manifest_cells = set()
    for e in entries:
        eco = e.get('economy')
        ind = e.get('indicator_id')
        if eco and ind:
            manifest_cells.add((eco, ind))

    gaps = []
    for key in sorted(inv_cells):
        if key not in manifest_cells:
            invs = inv_cells[key]
            laws = set()
            urls = set()
            for inv in invs:
                if inv.get('law_name'): laws.add(inv['law_name'])
                if inv.get('source'): urls.add(inv['source'])
                # Check URLs from the inventory
                for u in inv.get('urls', []):
                    urls.add(u)
            gaps.append({
                'economy': key[0], 'indicator': key[1],
                'laws': list(laws), 'urls': list(urls),
                'gap_type': 'FETCH_GAP'
            })

    # Find cells with short texts (< 5000 chars) - CORPUS_QUALITY
    for e in entries:
        eco = e.get('economy')
        ind = e.get('indicator_id')
        cc = e.get('char_count', 0)
        if cc and cc < 5000:
            gaps.append({
                'economy': eco, 'indicator': ind,
                'laws': [e.get('law_name', '')],
                'urls': e.get('urls', []),
                'gap_type': 'CORPUS_QUALITY',
                'char_count': cc,
                'text_path': e.get('text_path', '')
            })

    return gaps

def wb_search_law(query):
    """Search Wayback Machine for a law by name."""
    search_url = f'https://web.archive.org/cdx/search/cdx?url=*.{query}&output=json&limit=3&fl=original,timestamp,statuscode&matchType=host'
    try:
        req = urllib.request.Request(search_url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode())
        return data[1:] if len(data) > 1 else []
    except:
        return []

def try_fix_cell(gap):
    """Try to fix a gap cell by finding better text."""
    eco = gap['economy']
    ind = gap['indicator']
    gtype = gap['gap_type']
    laws = gap['laws']
    urls = gap.get('urls', [])
    
    print(f"\n{'='*60}")
    print(f"Fixing {eco} {ind} [{gtype}]")
    print(f"  Laws: {[l[:60] for l in laws[:2]]}")
    
    text = None
    source_url = None

    # Strategy 1: Try existing URLs via Wayback Machine
    for url in urls:
        if not url or url.startswith('file://'):
            continue
        print(f"  Trying via Wayback: {url[:80]}")
        text, ts = wb_fetch(url)
        if text and len(text) > 500:
            source_url = f"{url} (Wayback {ts})"
            print(f"  Got {len(text)} chars via Wayback!")
            break
        time.sleep(0.5)
    
    # Strategy 2: Try direct fetch for URLs that might work
    if not text:
        for url in urls:
            if not url or 'consultant.ru' in url or 'gov.cn' in url:
                continue
            print(f"  Trying direct: {url[:80]}")
            text = direct_fetch(url)
            if text and len(text) > 500:
                source_url = url
                print(f"  Got {len(text)} chars directly!")
                break
            time.sleep(0.5)
    
    # Strategy 3: Search for plain text/official gazette versions via web search
    # (We can't do web search programmatically without API, skip)
    
    if text and is_garbage_page(text):
        print(f"  Rejected at save: Wayback UI shell")
        text = None
    if text and len(text) >= 500:
        return save_text(eco, ind, text, source_url, laws[0] if laws else '')
    else:
        print(f"  FAILED: Could not find adequate text")
        return None

def save_text(eco, ind, text, source_url, law_name):
    """Save text to corpus and create/update manifest entry."""
    eco_dir = os.path.join(CORPUS_DIR, eco)
    os.makedirs(eco_dir, exist_ok=True)
    
    # Create a clean filename from law name
    slug = re.sub(r'[^a-z0-9]+', '-', law_name.lower())[:80].strip('-')
    if not slug:
        slug = f'{eco.lower()}-{ind.replace(".","-")}'
    fname = slug + '.txt'
    fpath = os.path.join(eco_dir, fname)
    
    # Avoid overwriting better texts
    if os.path.exists(fpath) and os.path.getsize(fpath) > len(text):
        print(f"  Existing file larger, keeping: {fpath}")
        return fpath
    
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(text)
    
    sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
    print(f"  Saved {len(text)} chars to {fname}")
    
    # Update manifest
    entries = load_manifest()
    # Remove old entry for this cell if exists
    entries = [e for e in entries if not (e.get('economy') == eco and e.get('indicator_id') == ind)]
    
    entry = {
        'economy': eco,
        'law_name': law_name,
        'indicator_id': ind,
        'urls': [source_url] if source_url else [],
        'text_path': f'data/round2_corpus/{eco}/{fname}',
        'status': 'ok',
        'char_count': len(text),
        'sha256': sha
    }
    entries.append(entry)
    save_manifest(entries)
    print(f"  Manifest updated")
    
    return fpath

def main():
    print("=" * 60)
    print("CORPUS AUTO-FIX SCRIPT")
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    entries = load_manifest()
    print(f"Loaded {len(entries)} manifest entries")
    
    gaps = find_gap_cells(entries)
    print(f"Found {len(gaps)} gap cells to fix")
    
    fixed = []
    failed = []
    
    for i, gap in enumerate(gaps):
        print(f"\n--- Gap {i+1}/{len(gaps)} ---")
        result = try_fix_cell(gap)
        if result:
            fixed.append((gap['economy'], gap['indicator'], gap['gap_type']))
        else:
            failed.append((gap['economy'], gap['indicator'], gap['gap_type']))
    
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(fixed)} fixed, {len(failed)} failed")
    print(f"Fixed: {fixed}")
    print(f"Failed: {failed}")
    print(f"Finished: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    return fixed, failed

if __name__ == '__main__':
    fixed, failed = main()
