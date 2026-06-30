from __future__ import annotations

import asyncio
from pathlib import Path

from browser_drivers import BrowserFetchError, OpenCliBrowserDriver
from legal_crawler.constants import _SSL_CTX
from legal_crawler.wayback import fetch_wayback_content

async def _precheck_url(url: str) -> str | None:
    """Check if a URL is dead before launching Playwright.

    Returns an error description string if the URL is dead
    (HTTP 404/410, DNS failure), or None if it's alive or uncertain.
    """
    import urllib.error
    _opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_SSL_CTX))
    _opener.addheaders = [("User-Agent", "Mozilla/5.0 (compatible; RDTII/1.0)")]

    def _check_sync() -> str | None:
        try:
            req = urllib.request.Request(url, method="HEAD")
            with _opener.open(req, timeout=10) as resp:
                if resp.status in (404, 410):
                    return f"HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return f"HTTP {e.code}"
            return None
        except urllib.error.URLError as e:
            reason = str(e.reason)
            if any(s in reason for s in [
                "Name or service not known", "nodename nor servname",
                "Temporary failure", "No address associated",
            ]):
                return f"DNS failure: {reason}"
            return None
        except Exception:
            return None
        return None

    try:
        return await asyncio.to_thread(_check_sync)
    except Exception:
        return None


# ── HTTP(S) direct fetch fallback ───────────────────────────────────────────
# Some government sites (e.g. sso.agc.gov.sg) use CDN WAFs (CloudFront)
# that block Playwright while allowing simple HTTP clients like httpx.
# This fallback tries plain HTTP before giving up.


async def _try_http_fallback(url: str, timeout: int = 30000) -> dict | None:
    """Fetch a URL via plain HTTP(S) — bypasses Playwright for WAF-blocked SSR sites.

    Tries two strategies:
      1. SSO-specific: look for the .legis container (Singapore legislation)
      2. Generic: extract <body> content

    Returns the same dict format as fetch_legal_content on success, or None.
    """
    import httpx

    print(f"[HTTP Fallback] 直接 HTTP 获取: {url}")
    try:
        client = httpx.Client(
            verify=False,
            timeout=httpx.Timeout(timeout / 1000),
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )
        resp = client.get(url)
        resp.raise_for_status()
        html = resp.text
        if len(html) < 1000:
            print(f"[HTTP Fallback] 内容过短 ({len(html)} 字符)，跳过")
            return None

        import re as _re
        import html as _html

        # Strategy 1: SSO-specific .legis container
        raw = None
        body_match = _re.search(
            r'<div\s+class="legis[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
            html, _re.DOTALL | _re.IGNORECASE,
        )
        if body_match:
            raw = body_match.group(1)

        # Strategy 2: generic <body> fallback
        if not raw:
            body_match = _re.search(r'<body[^>]*>(.*?)</body>', html, _re.DOTALL | _re.IGNORECASE)
            raw = body_match.group(1) if body_match else html

        text = _re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=_re.DOTALL | _re.IGNORECASE)
        text = _re.sub(r'<style[^>]*>.*?</style>', '', text, flags=_re.DOTALL | _re.IGNORECASE)
        text = _re.sub(r'<[^>]+>', ' ', text)
        text = _html.unescape(text)
        text = _re.sub(r'\s+', ' ', text).strip()

        if len(text) > 500:
            print(f"[HTTP Fallback] 成功！{len(text)} 字符")
            return {
                "type": "text",
                "url": url,
                "text": text,
                "metadata": {"source": "http_fallback"},
            }

        # ── SSO-specific: HTML too short (paged content), try PDF version ──
        pdf_match = _re.search(
            r'href=\"([^\"]+ViewType=Pdf[^\"]*)\"', html, _re.IGNORECASE
        )
        if not pdf_match:
            # Try appending ViewType=Pdf directly
            pdf_candidate = url + ("&" if "?" in url else "?") + "ViewType=Pdf"
        else:
            pdf_candidate = _re.sub(r'&amp;', '&', pdf_match.group(1))
            if pdf_candidate.startswith("/"):
                from urllib.parse import urlparse
                parsed = urlparse(url)
                pdf_candidate = f"{parsed.scheme}://{parsed.netloc}{pdf_candidate}"

        print(f"[HTTP Fallback] HTML 文本过短，尝试 PDF 版本: {pdf_candidate}")
        try:
            pdf_resp = client.get(pdf_candidate)
            pdf_resp.raise_for_status()
            if pdf_resp.headers.get("content-type", "").startswith("application/pdf"):
                import tempfile, os, uuid
                tmp = Path(tempfile.gettempdir()) / f"sso_{uuid.uuid4().hex}.pdf"
                tmp.write_bytes(pdf_resp.content)
                from pdf_reader import read_pdf
                try:
                    pdf_result = await asyncio.to_thread(read_pdf, str(tmp), source_url=pdf_candidate)
                    pdf_text = "\n".join(pdf_result.pages)
                finally:
                    os.unlink(str(tmp))
                if len(pdf_text) > 500:
                    print(f"[HTTP Fallback PDF] 成功！{len(pdf_text)} 字符")
                    return {
                        "type": "text",
                        "url": url,
                        "text": pdf_text,
                        "metadata": {"source": "http_fallback_pdf", "original_format": "pdf"},
                    }
        except Exception as pdf_e:
            print(f"[HTTP Fallback PDF] 失败: {pdf_e}")

        print(f"[HTTP Fallback] 提取文本过短 ({len(text)} 字符)")
    except Exception as e:
        print(f"[HTTP Fallback] 失败: {e}")
    return None


async def _try_wayback_fallback(url: str, context: str = "dead link") -> dict | None:
    """Try Wayback Machine fallback and log the attempt."""
    print(f"[Dead Link] {url} — {context}，尝试 Internet Archive 归档...")
    wb_result = await fetch_wayback_content(url)
    if wb_result["type"] == "text":
        print(f"[Wayback] 成功！归档于 {wb_result.get('metadata', {}).get('archive_timestamp', '?')}")
        return wb_result
    print(f"[Wayback] 未找到 '{url}' 的快照")
    return None


async def _try_opencli_fetch(url: str, timeout: int) -> dict | None:
    try:
        result = await OpenCliBrowserDriver().fetch_legal_content(url, timeout=timeout)
        if result.get("type") == "text" and result.get("text"):
            print(f"[OpenCLI] 成功提取 {len(result['text'])} 字符: {url}")
            return result
        return None
    except BrowserFetchError as e:
        print(f"[OpenCLI] 不可用或提取失败: {e}")
        return None
