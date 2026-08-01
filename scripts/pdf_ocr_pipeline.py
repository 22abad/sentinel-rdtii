#!/usr/bin/env python3
"""Standalone PDF download + OCR pipeline. No headful browser needed.
Targets: LAO, THA, IDN PDFs from official portals."""
import os, sys, json, hashlib, re, ssl, tempfile, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "pdf-reader"))
sys.path.insert(0, str(Path(__file__).parent.parent / "pdf-reader" / "ocr-service"))

CORPUS = Path("/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private/data/round2_corpus")
MANIFEST = Path("/Users/dxz/Documents/GitRepos/UN-DigitalTrade-AI-Mapper-private/data/round2_corpus/manifest.jsonl")

PDF_TARGETS = [
    # (url, economy, indicator, law_name, ocr_langs)
    ("https://www.laotradeportal.gov.la/upload/files/Legal_1557474430lo_LA.pdf",
     "LAO", "7.4", "Law on Electronic Data Protection No.25/NA (2017)", "eng+lao"),
    ("https://www.laotradeportal.gov.la/upload/files/Legal_1629270863lo_LA.pdf",
     "LAO", "12.3", "Decree on E-Commerce No.296/GoL (2021)", "eng+lao"),
]

def ocr_pdf(filepath, langs="eng+tha+chi_sim+ind"):
    """Run OCR via project's tesseract extractor. Falls back to PyMuPDF text extraction."""
    # Try text extraction first (PyMuPDF)
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(filepath)
        text = "\n".join(page.get_text() for page in doc)
        if len(text.strip()) > 500:
            return text
    except Exception:
        pass

    # Try OCR — execute from pdf-reader dir to resolve ocr_service imports
    try:
        import subprocess, json as jmod
        result = subprocess.run(
            ["python3", "-c", f"""
import sys; sys.path.insert(0, '.')
from ocr_service.tesseract_extractor import extract_text_ocr
pages = extract_text_ocr('{filepath}', langs='{langs}')
for p in pages: print(p)
"""],
            capture_output=True, text=True, timeout=180,
            cwd=str(Path(__file__).parent.parent / "pdf-reader")
        )
        text = result.stdout
        if len(text.strip()) > 200:
            return text
    except Exception as e:
        print(f"    OCR subprocess error: {e}")
        pages = extract_text_ocr(filepath, langs=langs)
        text = "\n".join(pages)
        if len(text.strip()) > 200:
            return text
    except Exception as e:
        print(f"    OCR error: {e}")

    return ""

def main():
    ctx = ssl._create_unverified_context()
    results = []

    for url, eco, ind, law_name, langs in PDF_TARGETS:
        print(f"\n[{eco} {ind}] {law_name}")
        print(f"  URL: {url[:80]}...")

        # Download
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=120, context=ctx)
            pdf_bytes = resp.read()
            print(f"  Downloaded {len(pdf_bytes)} bytes")
        except Exception as e:
            print(f"  ✗ Download failed: {e}")
            continue

        # OCR
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        text = ocr_pdf(tmp_path, langs)
        os.unlink(tmp_path)

        if text and len(text) > 500:
            # Save
            eco_dir = CORPUS / eco
            eco_dir.mkdir(parents=True, exist_ok=True)
            slug = re.sub(r'[^a-z0-9]+', '-', law_name.lower())[:80].strip('-')
            fpath = eco_dir / f"{slug}.txt"
            full = f"{law_name}\nSource: {url}\n\n{text}"
            fpath.write_text(full, encoding='utf-8')

            sha = hashlib.sha256(full.encode()).hexdigest()
            chars = len(full)
            print(f"  ✓ Saved: {chars} chars, sha={sha[:16]}...")

            # Manifest
            entries = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
            entries = [e for e in entries if not (e.get('economy')==eco and e.get('indicator_id')==ind)]
            entries.append({
                "economy": eco, "law_name": law_name, "indicator_id": ind,
                "urls": [url], "text_path": str(fpath.relative_to(CORPUS.parent)),
                "status": "ok", "char_count": chars, "sha256": sha
            })
            MANIFEST.write_text('\n'.join(json.dumps(e, ensure_ascii=False) for e in entries) + '\n')
            results.append((eco, ind, chars))
        else:
            print(f"  ✗ Too short: {len(text)} chars")

    print(f"\n=== Done: {len(results)}/{len(PDF_TARGETS)} ===")
    for eco, ind, chars in results:
        print(f"  {eco} {ind}: {chars} chars")

if __name__ == "__main__":
    main()
