#!/usr/bin/env python3
"""Headful browser scraper for legal texts behind JS-rendered portals.
Targets: legalinfo.mn (MNG), bpk.go.id (IDN), nbtc.go.th (THA).
Uses Playwright + stealth (already in requirements.txt)."""
import asyncio, os, json, hashlib, re
from pathlib import Path
from playwright.async_api import async_playwright

CORPUS = Path("/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private/data/round2_corpus")
MANIFEST = Path("/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private/data/round2_corpus/manifest.jsonl")

# ── Targets: (url, economy, indicator, law_name_hint) ─────────────────
TARGETS = [
    # MNG — legalinfo.mn (325 English translations available)
    ("https://legalinfo.mn/en/edtl/16532053734461", "MNG", "7.4",
     "Law on Personal Data Protection (2021)"),
    ("https://legalinfo.mn/en/detail/9491", "MNG", "3.4",
     "Law on Investment (2013)"),
    # IDN — bpk.go.id (IDN's official legislation portal)
    ("https://peraturan.bpk.go.id/Details/229798/uu-no-27-tahun-2022", "IDN", "7.1",
     "Law No.27 on Personal Data Protection (2022) full"),
    # THA — thailawforum (text-based)
    ("http://www.thailawforum.com/database1/telecom-business-act.html", "THA", "5.3",
     "Telecommunications Business Act B.E. 2544 (2001) full"),
    # LAO — laotradeportal
    ("https://www.laotradeportal.gov.la/upload/files/Legal_1557474430lo_LA.pdf", "LAO", "7.4",
     "Law on Electronic Data Protection No.25/NA (2017) — Lao PDF for OCR"),
]

async def scrape_page(page, url, timeout=30000):
    """Navigate to URL, wait for content, return page text."""
    print(f"  Navigating to {url[:80]}...")
    try:
        await page.goto(url, wait_until="networkidle", timeout=timeout)
        await page.wait_for_timeout(2000)  # extra wait for JS rendering
        text = await page.evaluate("document.body.innerText")
        return text
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

async def save_and_update(economy, indicator, law_name, text, url):
    """Save text to corpus and update manifest."""
    eco_dir = CORPUS / economy
    eco_dir.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r'[^a-z0-9]+', '-', law_name.lower())[:80].strip('-')
    fname = f"{slug}.txt"
    fpath = eco_dir / fname

    full_text = f"{law_name}\nSource: {url}\n\n{text}"
    fpath.write_text(full_text, encoding='utf-8')

    sha = hashlib.sha256(full_text.encode()).hexdigest()
    chars = len(full_text)

    # Update manifest
    entries = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    entries = [e for e in entries if not (e.get('economy')==economy and e.get('indicator_id')==indicator)]
    entries.append({
        "economy": economy, "law_name": law_name, "indicator_id": indicator,
        "urls": [url],
        "text_path": str(fpath.relative_to(CORPUS.parent)),
        "status": "ok", "char_count": chars, "sha256": sha
    })
    MANIFEST.write_text('\n'.join(json.dumps(e, ensure_ascii=False) for e in entries) + '\n')

    return chars, sha

PDF_TARGETS = [
    # PDFs to download + OCR (don't need headful browser, just curl + pdf-reader)
    ("https://www.laotradeportal.gov.la/upload/files/Legal_1557474430lo_LA.pdf", "LAO", "7.4",
     "Law on Electronic Data Protection No.25/NA (2017)"),
]

async def download_and_ocr(economy, indicator, law_name, url):
    """Download PDF and run OCR via the project's pdf-reader."""
    import subprocess, tempfile
    print(f"  Downloading PDF: {url[:80]}...")
    try:
        import urllib.request, ssl
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=60, context=ctx)
        pdf_bytes = resp.read()
        print(f"  Downloaded {len(pdf_bytes)} bytes")
    except Exception as e:
        print(f"  Download error: {e}")
        return None

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        # Try pdf-reader extraction (handles text + OCR)
        import subprocess, json as jmod
        result = subprocess.run(
            ["python3", "-c", f"""
import sys; sys.path.insert(0, 'pdf-reader')
from main import extract_sections
sections = extract_sections('{tmp_path}')
for s in sections:
    print(s.get('text','')[:500])
"""],
            capture_output=True, text=True, timeout=120,
            cwd="/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private"
        )
        text = result.stdout
        if len(text) < 500:
            # Try OCR fallback
            result2 = subprocess.run(
                ["python3", "-c", f"""
import sys; sys.path.insert(0, 'pdf-reader')
from ocr_service.tesseract_extractor import extract_text_ocr
text = extract_text_ocr('{tmp_path}')
print(text)
"""],
                capture_output=True, text=True, timeout=120,
                cwd="/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private"
            )
            if result2.stdout:
                text = result2.stdout
    except Exception as e:
        print(f"  OCR error: {e}")
        text = ""
    finally:
        os.unlink(tmp_path)

    if text and len(text) > 500:
        chars, sha = await save_and_update(economy, indicator, law_name, text, url)
        print(f"  ✓ OCR saved: {chars} chars")
        return chars
    print(f"  ✗ OCR failed (got {len(text)} chars)")
    return None

async def main():
    print("=== Headful Law Scraper + OCR ===\n")

    # Step 1: Headful browser scraping
    print("--- Step 1: Headful browser ---")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # JS-heavy sites need headful
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        page = await context.new_page()

        results = []
        for url, eco, ind, law_name in TARGETS:
            print(f"\n[{eco} {ind}] {law_name}")
            text = await scrape_page(page, url)
            if text and len(text) > 500:
                chars, sha = await save_and_update(eco, ind, law_name, text, url)
                print(f"  ✓ Saved: {chars} chars, sha={sha[:16]}...")
                results.append((eco, ind, chars))
            elif text:
                print(f"  ⚠ Too short: {len(text)} chars — skipping")
            else:
                print(f"  ✗ Failed")

        await browser.close()

    # Step 2: PDF download + OCR
    print("\n--- Step 2: PDF download + OCR ---")
    for url, eco, ind, law_name in PDF_TARGETS:
        print(f"\n[{eco} {ind}] {law_name}")
        chars = await download_and_ocr(eco, ind, law_name, url)
        if chars:
            results.append((eco, ind, chars))

    print(f"\n=== Done: {len(results)}/{len(TARGETS) + len(PDF_TARGETS)} total ===")
    for eco, ind, chars in results:
        print(f"  {eco} {ind}: {chars} chars")

if __name__ == "__main__":
    asyncio.run(main())
