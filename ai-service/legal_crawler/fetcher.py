from __future__ import annotations

import re
from collections import deque
from typing import Any, Dict, Optional
from urllib.parse import urljoin, urlparse

from browser_drivers import BrowserMode, normalize_browser_mode
from legal_crawler.browser import (
    async_playwright,
    _apply_stealth,
    _download_file,
    _extract_html_content,
    _initialize_browser_context,
    _read_docx,
    _wait_for_page_load,
)
from legal_crawler.constants import INVALID_URL_PATTERNS, KNOWN_ALTERNATIVES
from legal_crawler.fallbacks import _precheck_url, _try_http_fallback, _try_opencli_fetch, _try_wayback_fallback
from legal_crawler.ocs import fetch_thai_law_by_keyword
from legal_crawler.wayback import fetch_google_cache, fetch_wayback_content

async def fetch_legal_content(
    url: str,
    timeout: int = 60000,
    max_retries: int = 3,
    proxy: Optional[dict] = None,
    browser_mode: BrowserMode | str = "auto",
) -> Dict[str, Any]:
    """
    抓取法律内容（HTML 文本或 PDF）. 
    """
    mode = normalize_browser_mode(str(browser_mode))

    if any(re.match(pattern, url) for pattern in INVALID_URL_PATTERNS):
        return {"type": "error", "message": f"URL invalid: {url}"}

    path_lower = url.lower().split('?')[0]
    direct_file_url = path_lower.endswith((".pdf", ".doc", ".docx"))

    # When the user explicitly asks for OpenCLI, prefer the authorized local
    # browser session before cheap HTTP probes. File URLs still use the existing
    # downloader/parser path because the OpenCLI text bridge does not parse files.
    if mode == "opencli" and not direct_file_url:
        opencli_result = await _try_opencli_fetch(url, timeout)
        if opencli_result:
            return opencli_result
        print("[OpenCLI] primary path failed — falling back to HTTP / Playwright / archive fallback.")

    # ── Pre-check: dead link detection before launching Playwright ──
    dead_reason = await _precheck_url(url)
    if dead_reason:
        wb = await _try_wayback_fallback(url, dead_reason)
        if wb:
            return wb
        return {"type": "error", "message": f"Dead link ({dead_reason}), no Wayback snapshot"}

    # ── Direct HTTP probe (SSR sites like SSO block Playwright but serve
    # full content via plain HTTP — try it first to avoid Playwright overhead).
    http_result = await _try_http_fallback(url, timeout)
    if http_result:
        return http_result

    for attempt in range(1, max_retries + 1):
        async with async_playwright() as p:
            context = None
            try:
                context = await _initialize_browser_context(p, proxy=proxy)
                page = await context.new_page()
                await _apply_stealth(page)
                page.set_default_timeout(timeout)
                
                # Task: Check if direct PDF / Word URL to avoid ERR_ABORTED
                if path_lower.endswith(".pdf"):
                    print(f"detected direct PDF URL: {url}")
                    pdf_path = await _download_file(page, url)
                    if pdf_path:
                        return {"type": "pdf", "url": url, "pdf_path": pdf_path}

                if path_lower.endswith(".docx") or path_lower.endswith(".doc"):
                    print(f"detected Word document: {url}")
                    doc_path = await _download_file(page, url)
                    if doc_path:
                        if doc_path.endswith(".docx"):
                            doc_text = await _read_docx(doc_path)
                        else:
                            doc_text = None
                        if doc_text:
                            return {"type": "docx", "url": url, "text": doc_text}
                        return {"type": "error", "message": f"Word doc解析failed: {url}"}

                print(f"visiting: {url}")
                response = None
                try:
                    # Increase timeout and use wait_until="domcontentloaded" for potentially slow gov sites
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                    # Inline dead-link detection — catch 404/410 from Playwright response
                    if response and response.status in (404, 410):
                        print(f"[Dead Link] Playwright returned HTTP {response.status} — skipping retry — trying Wayback")
                        wb = await _try_wayback_fallback(url, f"HTTP {response.status}")
                        if wb:
                            return wb
                        return {"type": "error", "message": f"Dead link (HTTP {response.status}), no Wayback snapshot"}
                except Exception as e:
                    # If aborted but it's a PDF, we might still be able to download it
                    error_str = str(e).lower()
                    if "err_aborted" in error_str or "navigation was aborted" in error_str or "timeout" in error_str:
                        print(f"interrupt/timeout recovery — downloading directly: {url}")
                        pdf_path = await _download_file(page, url)
                        if pdf_path:
                            return {"type": "pdf", "url": url, "pdf_path": pdf_path}
                    raise e
                
                # Check current URL or content-type for PDF | 检查当前 URL 或内容类型是否为 PDF
                is_pdf = url.lower().split('?')[0].endswith(".pdf") or page.url.lower().split('?')[0].endswith(".pdf")
                if not is_pdf:
                    # Sometimes the URL doesn't end in .pdf but the content is PDF
                    try:
                        content_type = await page.evaluate("document.contentType")
                        if content_type == "application/pdf":
                            is_pdf = True
                    except: pass

                if is_pdf:
                    pdf_path = await _download_file(page, page.url)
                    if pdf_path:
                        return {"type": "pdf", "url": url, "pdf_path": pdf_path}
                
                await _wait_for_page_load(page, timeout)
                
                # 检测页面内的 PDF 链接
                pdf_links = await page.evaluate('Array.from(document.querySelectorAll(\'a[href$=".pdf"]\')).map(a => a.href)')
                valid_pdf_links = [l for l in pdf_links if not any(re.match(p, l) for p in INVALID_URL_PATTERNS)]
                
                if valid_pdf_links:
                    pdf_url = urljoin(page.url, valid_pdf_links[0])
                    pdf_path = await _download_file(page, pdf_url)
                    if pdf_path:
                        return {"type": "pdf", "url": url, "pdf_path": pdf_path}

                content = await _extract_html_content(page)
                if content:
                    # Detect common anti-bot / block / challenge pages
                    # Use content-length heuristic + known block page signatures
                    block_indicators = [
                        "access denied", "just a moment",
                        "please wait while we verify",
                        "performing security",
                        "รอสักครู่", "กำลังทำการตรวจสอบความปลอดภัย",
                        "cloudflare ray id", "ddos protection",
                        "generated by cloudfront", "request could not be satisfied",
                        "the request could not be satisfied",
                    ]
                    low = content.lower().strip()
                    # Only flag when content is short (< 5KB) AND contains block language
                    if len(content) < 5000 and any(ind in low for ind in block_indicators):
                        print(f"[WARNING] anti-scraping block detected ({content[:60].strip()}...)")
                        # Try HTTP fallback before raising
                        http_result = await _try_http_fallback(url, timeout)
                        if http_result:
                            return http_result
                        if mode == "auto":
                            opencli_result = await _try_opencli_fetch(url, timeout)
                            if opencli_result:
                                return opencli_result
                        raise Exception(f"Blocked by anti-bot protection")
                    return {
                        "type": "text",
                        "url": page.url,
                        "text": content,
                        "metadata": {
                            "source": "playwright",
                            "http_status": response.status if response else None,
                            "tls_verified": page.url.casefold().startswith("https://"),
                        },
                    }
                
                if mode == "auto":
                    opencli_result = await _try_opencli_fetch(url, timeout)
                    if opencli_result:
                        return opencli_result
                return {"type": "error", "message": "no snapshot forhas效内容"}
            except Exception as e:
                print(f"[retry {attempt}/{max_retries}] error: {e}")
                if attempt == max_retries:
                    if mode == "auto":
                        opencli_result = await _try_opencli_fetch(url, timeout)
                        if opencli_result:
                            return opencli_result

                    # ── 所hasretryfailed → trying KNOWN_ALTERNATIVES ──────────
                    parsed = urlparse(url)
                    domain = parsed.netloc.replace("www.", "")
                    alternatives = KNOWN_ALTERNATIVES.get(domain, [])
                    if alternatives:
                        print(f"[Fallback] {domain} has {len(alternatives)} alternative source(s) — trying…")
                        for alt in alternatives:
                            if alt["type"] == "search_ocs":
                                # ratchakitcha → OCS 替代: 提取 URL 中has意义的search词
                                # URL 格式: /search-result?keyword=xxx 或 /documents/xxx.pdf
                                parsed_url = urlparse(url)
                                
                                # trying从 ratchakitcha URL 路径中提取法条关键词
                                path_parts = [p for p in parsed_url.path.split("/") if p]
                                if "search" in "".join(path_parts).lower():
                                    search_query = dict(p.split("=") for p in parsed_url.query.split("&") if "=" in p).get("keyword", "")
                                else:
                                    search_query = ""

                                # 如果 URL 中无法提取has意义的关键词, 用文件名部分启发式推断
                                if not search_query or len(search_query) < 3:
                                    last_part = path_parts[-1] if path_parts else ""
                                    if "pdpa" in last_part.lower():
                                        search_query = "คุ้มครองข้อมูลส่วนบุคคล"
                                    elif "procurement" in last_part.lower() or "จัดซื้อ" in last_part.lower():
                                        search_query = "การจัดซื้อจัดจ้าง"
                                    elif "digital" in last_part.lower() or "ดิจิทัล" in last_part:
                                        search_query = "ดิจิทัลเพื่อเศรษฐกิจ"
                                    else:
                                        search_query = ""

                                if search_query:
                                    print(f"[Fallback] OCS search keyword: '{search_query}'")
                                    result = await fetch_thai_law_by_keyword(search_query, timeout=timeout)
                                    if result["type"] == "text":
                                        return result
                                else:
                                    print("[Fallback] could not infer OCS search keyword. ")
                                    print("[Fallback] ratchakitcha.soc.go.th possibly Cloudflare-blocked or insufficient URL info. ")
                                    print("hint: use fetch_thai_law_by_keyword('<thai-law-title>') to fetch from OCS. ")
                            elif alt["type"] == "web":
                                alt_url = f"https://www.{alt['source']}/"
                                print(f"[Fallback] trying alternative site: {alt_url}")
                                try:
                                    return await fetch_legal_content(alt_url, timeout=timeout, max_retries=1, browser_mode=mode)
                                except Exception as alt_e:
                                    print(f"[Fallback] alternative source failed: {alt_e}")
                                    continue

                    # ── HTTP Fallback (WAF-blocked SSR sites) ───────────
                    http_result = await _try_http_fallback(url, timeout)
                    if http_result:
                        return http_result

                    # ── Wayback Machine 兜底 ──
                    print(f"[Wayback Fallback] trying Internet Archive snapshot for '{url}'  snapshot...")
                    wb_result = await fetch_wayback_content(url)
                    if wb_result["type"] == "text":
                        return wb_result

                    # ── 最后trying Google Cache ──
                    print(f"[Google Cache Fallback] trying Google Cache...")
                    gc_text = await fetch_google_cache(url)
                    if gc_text:
                        return {
                            "type": "text",
                            "url": url,
                            "text": gc_text,
                            "metadata": {"source": "google_cache"},
                        }

                    if mode == "opencli":
                        return {
                            "type": "error",
                            "message": "OpenCLI browser mode could not extract this page, and the fallback sources also failed. Connect the OpenCLI browser bridge or switch Browser to Auto/Playwright.",
                        }
                    return {"type": "error", "message": str(e)}
            finally:
                if context:
                    await context.close()

async def crawl_for_pdpa_pdf(start_url: str, keyword: str = "Personal Data Protection", max_depth: int = 2, timeout: int = 60000) -> Optional[str]:
    """
    recursivesearch PDF. 
    """
    visited = set()
    queue = deque([(start_url, 0)])
    
    while queue:
        url, depth = queue.popleft()
        if url in visited or depth > max_depth:
            continue
        visited.add(url)
        
        print(f"[recursive] visit: {url} (depth{depth})")
        try:
            async with async_playwright() as p:
                context = await _initialize_browser_context(p)
                page = await context.new_page()
                await _apply_stealth(page)
                
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                await page.wait_for_timeout(5000) # 等待 Cloudflare 或 JS 挑战
                
                title = await page.title()
                print(f"[page title] {title}")
                
                if "Cloudflare" in title or "Just a moment" in title:
                    print("[WARNING] Cloudflare challenge — waiting longer...")
                    await page.wait_for_timeout(10000)
                    title = await page.title()
                    print(f"[re-checking title] {title}")
                if page.url.lower().endswith('.pdf') and keyword.lower() in page.url.lower():
                    pdf_path = await _download_file(page, page.url)
                    if pdf_path: return pdf_path
                
                # 2. 查找页面内所has链接
                links = await page.evaluate('Array.from(document.querySelectorAll("a")).map(a => ({href: a.href, text: a.innerText}))')
                
                for link in links:
                    href = link['href']
                    text = link['text']
                    
                    if not href or href in visited:
                        continue
                        
                    # 如果是 PDF 且包含关键词
                    if href.lower().endswith('.pdf') and (keyword.lower() in href.lower() or keyword.lower() in text.lower()):
                        print(f"[hit] found PDF: {href}")
                        pdf_path = await _download_file(page, href)
                        if pdf_path: return pdf_path
                    
                    # 如果是同站链接, 加入队列
                    if urlparse(href).netloc == urlparse(start_url).netloc:
                        queue.append((href, depth + 1))
                
                await context.close()
        except Exception as e:
            print(f"[error] {url}: {e}")
            
    return None
