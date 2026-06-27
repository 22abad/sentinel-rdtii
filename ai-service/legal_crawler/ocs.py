from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import quote

from legal_crawler.browser import async_playwright, _apply_stealth, _initialize_browser_context

# ── 泰国 OCS (Office of the Council of State) 法律库爬取 ─────────────
# OCS 网站 (https://www.ocs.go.th/searchlaw) 不依赖 Cloudflare，
# 可替代被 Cloudflare 保护的 ratchakitcha.soc.go.th（泰王國政府公報）。
# 其 SPA 阅读器 (https://searchlaw.ocs.go.th) 提供泰文 + 英文双语法律全文。

OCS_BASE = "https://www.ocs.go.th"
OCS_SEARCH = f"{OCS_BASE}/searchlaw"
OCS_SEARCH_ENG = f"{OCS_BASE}/searchlaw-law-eng"
OCS_DOC_READER = "https://searchlaw.ocs.go.th/council-of-state/#/public/doc"


async def search_ocs_law(
    query: str,
    search_topic: bool = True,
    max_results: int = 10,
    timeout: int = 30000,
) -> list[dict]:
    """在泰国 OCS 法律库按关键词搜索，返回法律列表。

    Args:
        query: 搜索关键词（泰文或英文）
        search_topic: True=按标题搜, False=按内容搜
        max_results: 最大返回条数
        timeout: 页面加载超时(ms)

    Returns:
        list of {title, year, doc_url, status, published_date, lang}
    """
    results: list[dict] = []
    async with async_playwright() as p:
        context = await _initialize_browser_context(p)
        try:
            page = await context.new_page()
            await _apply_stealth(page)

            encoded_q = quote(query)
            topic_param = "&topic=on" if search_topic else ""
            url = f"{OCS_SEARCH}?q={encoded_q}{topic_param}"
            print(f"[OCS 搜索] {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            await page.wait_for_timeout(4000)

            # OCS 的 SPA 异步加载结果列表，等待结果 DOM 出现
            try:
                await page.wait_for_selector(
                    'a[href*="/public/doc"]',
                    timeout=10000,
                )
            except Exception:
                # 可能无结果或页面结构不同
                body = await page.evaluate("document.body?.innerText || ''")
                if "ไม่พบข้อมูล" in body or "No results" in body:
                    print("[OCS 搜索] 未找到结果")
                    return []
                # fallback: 试着多等一会
                await page.wait_for_timeout(5000)

            # 提取所有法律文档链接
            links = await page.locator('a[href*="/public/doc"]').all()
            visited_ids: set[str] = set()
            for link in links:
                href = (await link.get_attribute("href")) or ""
                text = (await link.inner_text()).strip()
                if not text or not href:
                    continue
                # 每个 doc id 只取第一个标题
                doc_id = href.split("/public/doc/")[-1].split("?")[0]
                if doc_id in visited_ids:
                    continue
                visited_ids.add(doc_id)
                # 拼接完整 URL
                full_url = f"{OCS_DOC_READER}/{doc_id}"

                results.append({
                    "title": text,
                    "doc_id": doc_id,
                    "doc_url": full_url,
                    "lang": "th",
                    "source": "ocs.go.th",
                })
                if len(results) >= max_results:
                    break

            print(f"[OCS 搜索] 找到 {len(results)} 条结果")
            return results

        finally:
            await context.close()


async def fetch_ocs_law_document(
    doc_id: str,
    lang: str = "th",
    timeout: int = 30000,
) -> Optional[str]:
    """从 OCS SPA 阅读器提取法律全文（泰文或英文）。

    OCS 的 document viewer 是 React SPA，需要用 Playwright 渲染后
    才能获取全文。支持 ?lang=en 参数切换到英文版。

    Args:
        doc_id: OCS 文档 ID（从 search_ocs_law 返回的 doc_id）
        lang: "th"=泰文, "en"=英文
        timeout: 页面加载 + 渲染超时(ms)

    Returns:
        法律全文文本，失败返回 None
    """
    lang_param = "?lang=en" if lang == "en" else ""
    url = f"{OCS_DOC_READER}/{doc_id}{lang_param}"

    async with async_playwright() as p:
        context = await _initialize_browser_context(p)
        try:
            page = await context.new_page()
            await _apply_stealth(page)

            print(f"[OCS 文档] 正在加载: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            # SPA 需要额外时间渲染
            await page.wait_for_timeout(5000)

            # 检查页面是否成功加载
            title = await page.title()
            if "404" in title:
                print(f"[OCS 文档] 404 — doc_id 无效: {doc_id}")
                return None

            # 如果请求英文版，尝试点击 "Latest Translation" 按钮加载翻译内容
            if lang == "en":
                try:
                    trans_btn = page.locator(
                        'button:has-text("Translation"),'
                        'a:has-text("Latest Translation"),'
                        '[role="tab"]:has-text("Translation")'
                    ).first
                    if await trans_btn.count() > 0:
                        await trans_btn.click()
                        print("[OCS 文档] 点击了 Translation 按钮")
                        await page.wait_for_timeout(3000)
                except Exception:
                    pass

            # 获取全文 — 使用 body.innerText 获取所有可见文本
            body = await page.evaluate("document.body?.innerText || ''")
            if len(body) < 200:
                # 可能内容在某个深层容器里，等更久再试一次
                await page.wait_for_timeout(3000)
                body = await page.evaluate("document.body?.innerText || ''")

            if len(body) < 100:
                print(f"[OCS 文档] 提取的文本过短 ({len(body)} chars)，可能被拦截")
                return None

            print(f"[OCS 文档] 成功提取 {len(body)} 字符 ({lang})")
            return body

        finally:
            await context.close()


async def fetch_thai_law_by_keyword(
    query: str,
    lang: str = "th",
    timeout: int = 30000,
) -> Dict[str, Any]:
    """一站式泰国法律获取：关键词搜索 → 选取第一条 → 拉取全文。

    这是推荐给上层 /api/extract 调用的高级接口。
    自动处理：OCS 搜索 → SPA 渲染 → 全文提取。

    Args:
        query: 法律名称关键词（泰文）
        lang: "th"=泰文, "en"=英文
        timeout: 超时(ms)

    Returns:
        与 fetch_legal_content 同结构的 dict
    """
    results = await search_ocs_law(query, timeout=timeout)
    if not results:
        return {
            "type": "error",
            "message": f"OCS 未找到与 '{query}' 相关的法律",
        }

    best = results[0]
    text = await fetch_ocs_law_document(best["doc_id"], lang=lang, timeout=timeout)
    if not text:
        return {
            "type": "error",
            "message": f"OCS 文档提取失败: {best['doc_url']}",
        }

    return {
        "type": "text",
        "url": best["doc_url"],
        "text": text,
        "metadata": {
            "title": best["title"],
            "doc_id": best["doc_id"],
            "lang": lang,
            "source": "ocs.go.th",
        },
    }
