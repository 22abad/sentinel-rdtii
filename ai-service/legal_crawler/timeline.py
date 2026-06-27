from __future__ import annotations

import asyncio
import urllib.request

from legal_crawler.constants import _SSL_CTX
from legal_crawler.wayback import fetch_wayback_closest

async def verify_law_timeline(
    url: str,
    llm_claimed_date: str = "",
) -> dict:
    """核实法律文档的版本时间戳。

    Args:
        url: 法律文档的 URL
        llm_claimed_date: LLM 提取的 last_update 字符串

    Returns:
        {
            "verified": bool,          # 是否通过验证
            "sources_checked": int,    # 核实的来源数
            "best_date": str,          # 最佳确认日期
            "verification_log": str,   # 核验过程描述（用于 audit trail）
            "source_details": [        # 每个来源的详细结果
                {"source": str, "date": str, "status": str}
            ]
        }
    """
    from datetime import datetime

    source_details: list[dict] = []

    # 1. Wayback Machine CDX — 查看历史变更
    snapshot = await fetch_wayback_closest(url)
    wb_date = ""
    if snapshot:
        ts = snapshot["timestamp"]
        if len(ts) >= 8:
            try:
                wb_date = datetime.strptime(ts[:8], "%Y%m%d").strftime("%Y-%m-%d")
            except ValueError:
                wb_date = ts[:8]
        source_details.append({
            "source": "wayback_machine",
            "date": wb_date,
            "status": "found" if wb_date else "no_date",
        })

    # 2. HTTP Last-Modified 头
    http_date = ""
    _opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_SSL_CTX))
    try:
        def _fetch_head():
            req = urllib.request.Request(url, method="HEAD")
            resp = _opener.open(req, timeout=10)
            return resp.headers.get("Last-Modified", "")
        http_date_str = await asyncio.to_thread(_fetch_head)
        if http_date_str:
            try:
                parsed = datetime.strptime(http_date_str, "%a, %d %b %Y %H:%M:%S %Z")
                http_date = parsed.strftime("%Y-%m-%d")
            except ValueError:
                http_date = http_date_str
        source_details.append({
            "source": "http_last_modified",
            "date": http_date or "unavailable",
            "status": "found" if http_date else "header_missing",
        })
    except Exception as e:
        source_details.append({
            "source": "http_last_modified",
            "date": "",
            "status": f"error: {str(e)[:60]}",
        })

    # 3. 交叉比较
    verified = False
    best_date = llm_claimed_date
    verification_log_parts: list[str] = []

    all_dates = [d for d in [llm_claimed_date, wb_date, http_date] if d]
    unique_dates = set(all_dates)

    if llm_claimed_date:
        verification_log_parts.append(f"LLM 声称: {llm_claimed_date}")
    if wb_date:
        verification_log_parts.append(f"Wayback 归档: {wb_date}")
    if http_date:
        verification_log_parts.append(f"HTTP 头: {http_date}")

    if len(unique_dates) == 1 and len(all_dates) >= 2:
        verified = True
        verification_log_parts.append("✅ 所有来源日期一致")
    elif llm_claimed_date and wb_date and llm_claimed_date != wb_date:
        verification_log_parts.append(f"⚠️ LLM 声称 ({llm_claimed_date}) 与 Wayback ({wb_date}) 不一致")
        # 偏向信任 Wayback Machine
        best_date = wb_date
    elif llm_claimed_date and http_date and llm_claimed_date != http_date:
        verification_log_parts.append(f"⚠️ LLM 声称 ({llm_claimed_date}) 与 HTTP 头 ({http_date}) 不一致")
        best_date = http_date

    log_str = "; ".join(verification_log_parts)

    return {
        "verified": verified,
        "sources_checked": len(source_details),
        "best_date": best_date,
        "verification_log": log_str,
        "source_details": source_details,
    }

