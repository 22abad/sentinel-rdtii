from __future__ import annotations

import asyncio
import json
import re
import urllib.request
from typing import Any, Dict, Optional

from legal_crawler.browser import async_playwright, _apply_stealth, _initialize_browser_context
from legal_crawler.constants import _SSL_CTX

# ── Wayback Machine 回溯取证 ────────────────────────────────────────
# 当源站被 WAF/Cloudflare 阻断时，通过 Internet Archive 获取历史快照。
# 三层策略：
#   1. CDX API 查询最近快照
#   2. 获取快照内容
#   3. 返回带时间戳的归档元数据

WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx"
WAYBACK_AVAIL = "https://archive.org/wayback/available"
WAYBACK_WEB = "https://web.archive.org/web"


async def fetch_wayback_closest(url: str, max_retries: int = 2) -> Optional[dict]:
    """通过 Wayback Machine CDX API 查找最近的可用快照。"""
    _opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_SSL_CTX))
    _opener.addheaders = [("User-Agent", "Mozilla/5.0 (compatible; RDTII/1.0)")]

    for attempt in range(max_retries):
        try:
            def _fetch_avail():
                avail_url = f"{WAYBACK_AVAIL}?url={url}"
                resp = _opener.open(avail_url, timeout=15)
                return json.loads(resp.read())

            data = await asyncio.to_thread(_fetch_avail)
            snapshots = data.get("archived_snapshots", {})
            closest = snapshots.get("closest", {})
            if closest.get("available") and closest.get("url"):
                ts = closest.get("timestamp", "")
                archive_url = closest["url"]
                print(f"[Wayback] 快照: {ts} → {archive_url}")
                return {
                    "timestamp": ts.replace("-", "").replace(":", "").replace(" ", ""),
                    "archive_url": archive_url,
                    "statuscode": "200",
                    "source": "wayback_availability",
                }

            # CDX fallback
            def _fetch_cdx():
                cdx_url = f"{WAYBACK_CDX}?url={url}&output=json&limit=5&fl=timestamp,original,statuscode&sort=reverse"
                resp = _opener.open(cdx_url, timeout=15)
                return json.loads(resp.read())

            rows = await asyncio.to_thread(_fetch_cdx)
            if len(rows) > 1:
                for row in rows[1:]:
                    ts, orig, sc = row[0], row[1], row[2] if len(row) > 2 else "200"
                    if sc in ("200", "302"):
                        archive_url = f"{WAYBACK_WEB}/{ts}/{orig}"
                        print(f"[Wayback CDX] 快照: {ts} ({sc})")
                        return {
                            "timestamp": ts,
                            "archive_url": archive_url,
                            "statuscode": sc,
                            "source": "wayback_cdx",
                        }
        except Exception as e:
            print(f"[Wayback] 查询失败 (attempt {attempt+1}): {e}")
            await asyncio.sleep(1)

    return None


async def fetch_wayback_content(url: str, timeout: int = 30000) -> Dict[str, Any]:
    """从 Wayback Machine 获取法律内容。

    三部曲：
        1. CDX → 找最近快照
        2. 获取快照 HTML/文本
        3. 返回内容 + 归档元数据

    Returns:
        同 fetch_legal_content 格式，附加 archive_timestamp 字段
    """
    snapshot = await fetch_wayback_closest(url)
    if not snapshot:
        return {"type": "error", "message": "Wayback Machine 中未找到该 URL 的快照"}

    archive_url = snapshot["archive_url"]
    print(f"[Wayback] 正在获取快照内容: {archive_url}")

    # 尝试直接用 HTTP 获取文本（避免启动 Playwright）
    import html as html_mod

    _opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_SSL_CTX))
    _opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (compatible; RDTII/1.0; +https://github.com/22abad/UN-DigitalTrade-AI-Mapper)"),
    ]

    try:
        def _fetch():
            resp = _opener.open(archive_url, timeout=int(timeout / 1000))
            return resp.read().decode("utf-8", errors="replace")

        raw_html = await asyncio.to_thread(_fetch)
        text = re.sub(r'<[^>]+>', ' ', raw_html)
        text = html_mod.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 200:
            # Detect garbage (Wayback wrapper JS, block pages)
            garbage_signals = ["window.addEventListener", "archive_analytics",
                               "webpackJsonp", "performing security"]
            if any(s in text[:500].lower() for s in garbage_signals):
                print(f"[Wayback] HTTP 获取成功但内容为 Wayback 包装页面 ({len(text)} 字符)")
            else:
                print(f"[Wayback] HTTP 获取成功: {len(text)} 字符 (归档于 {snapshot['timestamp']})")
                return {
                    "type": "text",
                    "url": archive_url,
                    "original_url": url,
                    "text": text,
                    "metadata": {
                        "source": "wayback_machine",
                        "archive_timestamp": snapshot["timestamp"],
                        "archive_url": archive_url,
                    },
                }
    except Exception as e:
        print(f"[Wayback] HTTP 获取失败: {e}")

    # HTTP 失败 → 用 Playwright 渲染（JS 站点）
    print(f"[Wayback] HTTP 不满足，启动 Playwright 渲染快照...")
    return await _fetch_wayback_with_playwright(archive_url, snapshot)


async def _fetch_wayback_with_playwright(archive_url: str, snapshot: dict) -> Dict[str, Any]:
    """用 Playwright 渲染 Wayback 快照页面。"""
    async with async_playwright() as p:
        context = await _initialize_browser_context(p)
        try:
            page = await context.new_page()
            await _apply_stealth(page)

            await page.goto(archive_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            body = await page.evaluate("document.body?.innerText || ''")
            if len(body) > 200:
                print(f"[Wayback Playwright] 成功: {len(body)} 字符")
                return {
                    "type": "text",
                    "url": archive_url,
                    "original_url": snapshot.get("original", archive_url),
                    "text": body,
                    "metadata": {
                        "source": "wayback_machine",
                        "archive_timestamp": snapshot["timestamp"],
                        "archive_url": archive_url,
                    },
                }
            return {"type": "error", "message": f"Wayback 快照无内容 ({len(body)} chars)"}
        finally:
            await context.close()


async def fetch_google_cache(url: str) -> Optional[str]:
    """Google Cache 快速取证——轻量级，无需 Playwright。

    注意：Google Cache 可能返回旧版或不可用。
    """
    import html as html_mod

    _opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_SSL_CTX))
    _opener.addheaders = [("User-Agent", "Mozilla/5.0 (compatible; RDTII/1.0)")]

    cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
    try:
        def _fetch():
            resp = _opener.open(cache_url, timeout=15)
            return resp.read().decode("utf-8", errors="replace")
        text = await asyncio.to_thread(_fetch)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = html_mod.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 200:
            return text
    except Exception as e:
        print(f"[Google Cache] 失败: {e}")
    return None


# ── 法律时间戳核实 ──────────────────────────────────────────────────
# 三重验证 LLM 声称的 `last_update` 日期：
#   1. Wayback Machine CDX — 查该 URL 历史变更
#   2. HTTP Last-Modified 头
