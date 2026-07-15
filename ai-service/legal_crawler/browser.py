from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page, async_playwright

from legal_crawler.constants import DOWNLOADS_DIR

# ── playwright-stealth 跨版本兼容 ──────────────────────────────────
# 1.x API:  from playwright_stealth import stealth_async; await stealth_async(page)
# 2.x API:  from playwright_stealth import Stealth; await Stealth().apply_stealth_async(page)
try:
    from playwright_stealth import Stealth
    _stealth = Stealth()
except ImportError:
    from playwright_stealth import stealth_async
    _stealth = type("_StealthCompat", (), {"stealth_async": staticmethod(stealth_async)})()

async def _apply_stealth(page: Page) -> None:
    if hasattr(_stealth, 'apply_stealth_async'):
        await _stealth.apply_stealth_async(page)
    elif hasattr(_stealth, 'stealth_async'):
        await _stealth.stealth_async(page)
    else:
        # fallback: inject basic evasion scripts manually
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        """)

async def _initialize_browser_context(playwright_instance: Any, proxy: Optional[dict] = None) -> BrowserContext:
    """
    初始化浏览器上下文, 并注入 stealth 插件. 
    """
    launch_args = {
        "headless": True,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--window-position=0,0",
            "--ignore-certifcate-errors",
            "--ignore-certifcate-errors-spki-list",
        ]
    }
    if proxy:
        launch_args["proxy"] = proxy
    browser = await playwright_instance.chromium.launch(**launch_args)
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        locale="en-US",
        viewport={"width": 1920, "height": 1080},
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
        },
    )
    return context

async def _wait_for_page_load(page: Page, timeout: int) -> None:
    """
    等待页面加载完成, 处理 JS 渲染. 
    """
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
        await page.wait_for_load_state("domcontentloaded", timeout=timeout)
    except Exception:
        pass

async def _download_file(page: Page, file_url: str, filename: Optional[str] = None) -> Optional[str]:
    """
    下载文件（PDF / Word / 任意类型）到本地. 
    """
    try:
        parsed_url = urlparse(file_url)
        filename = f"downloaded_{uuid.uuid4().hex}.bin"
        downloads_root = Path(DOWNLOADS_DIR).resolve()
        local_path = (downloads_root / filename).resolve()
        if downloads_root not in local_path.parents:
            raise ValueError("Invalid download filename")
        
        domain = f"{parsed_url.scheme}://{parsed_url.netloc}/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": domain,
            "Accept": "application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        response = await page.request.get(file_url, headers=headers, timeout=30000)
        if response.ok:
            with open(local_path, "wb") as f:
                f.write(await response.body())
            print(f"file downloaded to: {local_path}")
            return str(local_path)
        return None
    except Exception as e:
        print(f"error downloading file {file_url}: {e}")
        return None


async def _read_docx(path: str) -> Optional[str]:
    """用 python-docx 提取 .docx 文本. """
    try:
        from docx import Document
        doc = Document(path)
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return text if text.strip() else None
    except Exception as e:
        print(f"failed to read docx {path}: {e}")
        return None

async def _extract_html_content(page: Page) -> str:
    """
    提取 HTML 页面正文. 
    """
    selectors = [
        # Site-generic content selectors
        "main", "article", "section[role=main]", "[role=main]",
        ".main-content", ".mainContent", ".content-main",
        "#content", ".content", ".entry-content", ".post-content", ".body-content",
        # SSO / Singapore legislation selectors
        ".legis .body", ".legis", ".prov1Txt", ".pTxt", ".def",
        "body"
    ]
    for selector in selectors:
        try:
            element = page.locator(selector).first
            if await element.count() > 0:
                text_content = await element.text_content()
                if text_content and text_content.strip():
                    cleaned_text = re.sub(r'\s*\n\s*', '\n', text_content).strip()
                    if len(cleaned_text) > 100:
                        return cleaned_text
        except Exception:
            continue
    
    body_content = await page.evaluate("document.body.innerText")
    if body_content:
        return re.sub(r'\s*\n\s*', '\n', body_content).strip()
    return ""
