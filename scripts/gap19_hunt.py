#!/usr/bin/env python3
"""Targeted hunt for remaining 19 text-gap cells.
Strategy: headful browser for CHN + LAO URLs, Wayback Machine for dead links."""
import asyncio, json, hashlib, os, ssl, re, urllib.request
from pathlib import Path

CORPUS = Path("data/round2_corpus")
MANIFEST = Path("data/round2_corpus/manifest.jsonl")

# ── Targets with URLs we can actually reach ──
TARGETS = [
    # CHN — MOFCOM/gov.cn PDFs (try Wayback + alternative mirrors)
    ("CHN", "10.3", "Notice concerning Further Implementing Regulations on the Management of Online Foreign Film and Television Dramas",
     "https://www.chinafilm.gov.cn/xxgk/zcfg/gfxwj/dyfxfyjck/201409/t20140902_1508.html"),
    # LAO — lsp.moic.gov.la (JS-rendered, try headful)
    ("LAO", "5.4", "Law on Telecommunications No.09/NA 2011",
     "http://lsp.moic.gov.la/index.php?r=site%2Fdisplaylegal&id=55#7"),
]

def fetch_direct(url):
    """Try direct HTTP fetch (for sites that allow it)."""
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=30, context=ctx)
        return resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        return None

def fetch_wayback(url):
    """Try Wayback Machine for dead links."""
    cdx_url = f"https://web.archive.org/cdx/search/cdx?url={urllib.request.quote(url, safe='/:?=&')}&output=json&limit=3&fl=timestamp,original,statuscode"
    ctx = ssl._create_unverified_context()
    try:
        req = urllib.request.Request(cdx_url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30, context=ctx)
        data = json.loads(resp.read().decode())
        if len(data) <= 1:
            return None
        snapshots = data[1:]
        snapshots.sort(key=lambda x: (x[2]=='200', x[0]), reverse=True)
        ts, orig, status = snapshots[0]
        wb_url = f"https://web.archive.org/web/{ts}/{orig}"
        req2 = urllib.request.Request(wb_url, headers={"User-Agent": "Mozilla/5.0"})
        resp2 = urllib.request.urlopen(req2, timeout=60, context=ctx)
        content = resp2.read()
        # Clean HTML
        if b'<html' in content[:500]:
            from html.parser import HTMLParser
            class Cleaner(HTMLParser):
                def __init__(self):
                    super().__init__(); self.text = []
                def handle_data(self, data):
                    t = data.strip()
                    if t and len(t) > 10: self.text.append(t)
                def handle_starttag(self, tag, attrs):
                    if tag in ('script','style','noscript'): self.text.append('\n')
            c = Cleaner(); c.feed(content.decode('utf-8','replace'))
            text = '\n'.join(c.text)
        else:
            text = content.decode('utf-8', errors='replace')
        return text if len(text) > 500 else None
    except Exception:
        return None

def save(eco, ind, law_name, text, url, source_note=""):
    eco_dir = CORPUS / eco; eco_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r'[^a-z0-9]+','-',law_name.lower())[:80].strip('-')
    fname = f"{slug}.txt"
    fpath = eco_dir / fname
    full = f"{law_name}\nSource: {url} {source_note}\n\n{text}"
    fpath.write_text(full, encoding='utf-8')
    sha = hashlib.sha256(full.encode()).hexdigest()
    chars = len(full)
    # Manifest
    entries = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    entries = [e for e in entries if not (e.get('economy')==eco and e.get('indicator_id')==ind)]
    entries.append({"economy":eco,"law_name":law_name,"indicator_id":ind,"urls":[url+f" {source_note}"],"text_path":str(fpath),"status":"ok","char_count":chars,"sha256":sha})
    MANIFEST.write_text('\n'.join(json.dumps(e,ensure_ascii=False) for e in entries)+'\n')
    return chars

print("=== Gap-19 Targeted Hunt ===")
for eco, ind, law, url in TARGETS:
    print(f"\n[{eco} {ind}] {law[:60]}")
    print(f"  URL: {url[:80]}")

    # Try direct first
    text = fetch_direct(url)
    if text and len(text) > 500:
        chars = save(eco, ind, law, text, url, "(direct)")
        print(f"  ✓ Direct: {chars} chars")
        continue

    # Try Wayback
    text = fetch_wayback(url)
    if text and len(text) > 500:
        chars = save(eco, ind, law, text, url, "(Wayback)")
        print(f"  ✓ Wayback: {chars} chars")
        continue

    print(f"  ✗ Failed")

print("\nDone. Re-run with headful scraper if needed for JS-portal URLs.")
