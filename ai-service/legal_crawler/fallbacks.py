from __future__ import annotations

import asyncio
import html as html_module
import re
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

from browser_drivers import BrowserFetchError, OpenCliBrowserDriver
from legal_crawler.constants import _SSL_CTX
from legal_crawler.wayback import fetch_wayback_content


_EPUB_VOLUME_PATH_PATTERN = re.compile(
    r"/epub/OEBPS/document_\d+/document_\d+\.html$",
    flags=re.IGNORECASE,
)


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
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout / 1000),
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            direct_pdf_result = await _http_pdf_response_result(
                resp,
                source_url=url,
                fetch_method="http_fallback_pdf",
            )
            if direct_pdf_result:
                return direct_pdf_result

            html = resp.text
            if len(html) < 1000:
                print(f"[HTTP Fallback] 内容过短 ({len(html)} 字符)，跳过")
                return None

            # Prefer the actual embedded law/PDF over extracting a shell page.
            embedded_result = await _try_embedded_document(
                client,
                markup=html,
                container_url=str(resp.url),
            )
            if embedded_result:
                return embedded_result

            import html as _html
            import re as _re

            # Strategy 1: SSO-specific .legis container
            raw = None
            body_match = _re.search(
                r'<div\s+class="legis[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
                html,
                _re.DOTALL | _re.IGNORECASE,
            )
            if body_match:
                raw = body_match.group(1)

            # Strategy 2: generic <body> fallback
            if not raw:
                body_match = _re.search(
                    r"<body[^>]*>(.*?)</body>",
                    html,
                    _re.DOTALL | _re.IGNORECASE,
                )
                raw = body_match.group(1) if body_match else html

            text = _re.sub(
                r"<script[^>]*>.*?</script>",
                "",
                raw,
                flags=_re.DOTALL | _re.IGNORECASE,
            )
            text = _re.sub(
                r"<style[^>]*>.*?</style>",
                "",
                text,
                flags=_re.DOTALL | _re.IGNORECASE,
            )
            text = _re.sub(r"<[^>]+>", " ", text)
            text = _html.unescape(text)
            text = _re.sub(r"\s+", " ", text).strip()

            if (
                len(text) > 500
                and _has_legal_signal(text)
                and not _looks_like_error_or_challenge(text)
            ):
                print(f"[HTTP Fallback] 成功！{len(text)} 字符")
                return {
                    "type": "text",
                    "url": str(resp.url),
                    "text": text,
                    "metadata": {
                        "source": "http_fallback",
                        "http_status": resp.status_code,
                        "tls_verified": _response_tls_verified(resp),
                        "document_origin_domain": (urlsplit(str(resp.url)).hostname or "").casefold(),
                    },
                }

            # SSO and similar sites sometimes expose a PDF view separately.
            pdf_match = _re.search(
                r'href="([^"]+ViewType=Pdf[^"]*)"',
                html,
                _re.IGNORECASE,
            )
            if not pdf_match:
                pdf_candidate = url + ("&" if "?" in url else "?") + "ViewType=Pdf"
            else:
                pdf_candidate = _re.sub(r"&amp;", "&", pdf_match.group(1))
                if pdf_candidate.startswith("/"):
                    from urllib.parse import urlparse

                    parsed = urlparse(url)
                    pdf_candidate = f"{parsed.scheme}://{parsed.netloc}{pdf_candidate}"

            print(f"[HTTP Fallback] HTML 文本过短，尝试 PDF 版本: {pdf_candidate}")
            try:
                pdf_resp = await client.get(pdf_candidate)
                pdf_resp.raise_for_status()
                pdf_result = await _http_pdf_response_result(
                    pdf_resp,
                    source_url=pdf_candidate,
                    fetch_method="http_fallback_pdf",
                )
                if pdf_result:
                    return pdf_result
            except Exception as pdf_exc:
                print(f"[HTTP Fallback PDF] 失败: {pdf_exc}")

            print(f"[HTTP Fallback] 提取文本过短 ({len(text)} 字符)")
    except Exception as e:
        print(f"[HTTP Fallback] 失败: {e}")
    return None


async def _http_pdf_response_result(
    response,
    *,
    source_url: str,
    fetch_method: str,
) -> dict | None:
    """Parse an HTTP response as PDF even when its URL has no .pdf suffix."""
    content_type = response.headers.get("content-type", "").casefold()
    if "application/pdf" not in content_type and not response.content.startswith(b"%PDF"):
        return None
    if len(response.content) > 25 * 1024 * 1024:
        print(f"[HTTP PDF] 文件过大，跳过: {source_url}")
        return None

    import tempfile

    with tempfile.NamedTemporaryFile(prefix="http_pdf_", suffix=".pdf", delete=False) as handle:
        handle.write(response.content)
        tmp_path = Path(handle.name)
    from pdf_reader import read_pdf

    try:
        pdf_result = await asyncio.to_thread(
            read_pdf,
            str(tmp_path),
            source_url=source_url,
        )
        document_text = "\n".join(pdf_result.pages)
    finally:
        tmp_path.unlink(missing_ok=True)
    if len(document_text) <= 500:
        return None

    print(f"[HTTP PDF] 成功！{len(document_text)} 字符")
    return {
        "type": "text",
        "url": str(response.url),
        "text": document_text,
        "metadata": {
            "source": fetch_method,
            "original_format": "pdf",
            "http_status": response.status_code,
            "tls_verified": _response_tls_verified(response),
            "document_origin_domain": (urlsplit(str(response.url)).hostname or "").casefold(),
        },
    }


def _response_tls_verified(response) -> bool:
    """httpx only returns an HTTPS response after normal TLS checks succeed."""
    return urlsplit(str(response.url)).scheme.casefold() == "https"


async def _try_embedded_document(client, *, markup: str, container_url: str) -> dict | None:
    """Extract same-origin law text embedded in an iframe or PDF viewer."""
    document_urls = _embedded_document_urls(markup, container_url)[:5]
    combine_documents = _is_numbered_epub_volume_set(document_urls)
    document_parts: list[str] = []
    fetched_urls: list[str] = []
    formats: set[str] = set()
    http_statuses: list[int] = []
    tls_verified = True
    prefetched_responses: dict[str, object] = {}

    if combine_documents:
        rows = await asyncio.gather(
            *(_fetch_embedded_response(client, document_url) for document_url in document_urls)
        )
        prefetched_responses = {
            document_url: response
            for document_url, response in zip(document_urls, rows, strict=True)
            if response is not None
        }

    for document_url in document_urls:
        response = (
            prefetched_responses.get(document_url)
            if combine_documents
            else await _fetch_embedded_response(client, document_url)
        )
        if response is None:
            continue

        content_type = response.headers.get("content-type", "").casefold()
        is_pdf = "application/pdf" in content_type or response.content.startswith(b"%PDF")
        if is_pdf:
            if len(response.content) > 25 * 1024 * 1024:
                print(f"[HTTP Embedded PDF] 文件过大，跳过: {document_url}")
                continue
            import tempfile

            with tempfile.NamedTemporaryFile(prefix="embedded_", suffix=".pdf", delete=False) as handle:
                handle.write(response.content)
                tmp_path = Path(handle.name)
            from pdf_reader import read_pdf

            try:
                pdf_result = await asyncio.to_thread(
                    read_pdf,
                    str(tmp_path),
                    source_url=str(response.url),
                )
                document_text = "\n".join(pdf_result.pages)
            finally:
                tmp_path.unlink(missing_ok=True)
            if len(document_text) > 500:
                document_parts.append(document_text)
                fetched_urls.append(str(response.url))
                formats.add("pdf")
                http_statuses.append(response.status_code)
                tls_verified = tls_verified and _response_tls_verified(response)
                if not combine_documents:
                    break
            continue

        embedded_text = _html_text(response.text)
        if len(embedded_text) > 500 and _has_legal_signal(embedded_text):
            document_parts.append(embedded_text)
            fetched_urls.append(str(response.url))
            formats.add("html")
            http_statuses.append(response.status_code)
            tls_verified = tls_verified and _response_tls_verified(response)
            if not combine_documents:
                break

    if not document_parts:
        return None

    original_format = next(iter(formats)) if len(formats) == 1 else "mixed"
    fetch_method = f"http_fallback_embedded_{original_format}"
    document_text = "\n\n".join(document_parts)
    print(
        f"[HTTP Embedded {original_format.upper()}] 成功！"
        f"{len(document_text)} 字符，{len(document_parts)} 个文档部分"
    )
    return {
        "type": "text",
        "url": fetched_urls[0],
        "text": document_text,
        "metadata": {
            "source": fetch_method,
            "original_format": original_format,
            "http_status": http_statuses[0],
            "container_url": container_url,
            "embedded_document_urls": fetched_urls,
            "embedded_document_count": len(fetched_urls),
            "embedded_document_http_statuses": http_statuses,
            "embedded_document_origin_domains": sorted({
                (urlsplit(url).hostname or "").casefold()
                for url in fetched_urls
            }),
            "tls_verified": tls_verified,
            "document_origin_domain": (urlsplit(fetched_urls[0]).hostname or "").casefold(),
        },
    }


async def _fetch_embedded_response(client, document_url: str):
    try:
        response = await client.get(document_url)
        response.raise_for_status()
        return response
    except Exception as exc:
        print(f"[HTTP Embedded Document] 获取失败: {document_url} ({exc})")
        return None


def _is_numbered_epub_volume_set(urls: list[str]) -> bool:
    if len(urls) < 2:
        return False
    return all(
        _EPUB_VOLUME_PATH_PATTERN.search(urlsplit(url).path)
        for url in urls
    )


def _embedded_document_urls(markup: str, container_url: str) -> list[str]:
    urls: list[str] = []
    container_origin = _url_origin(container_url)
    if container_origin is None:
        return urls
    attributes = re.findall(
        r"<iframe\b[^>]*?\b(?:data-src|src)\s*=\s*(['\"])(.*?)\1",
        markup,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for _quote, raw_value in attributes:
        iframe_url = urljoin(container_url, html_module.unescape(raw_value).strip())
        parsed_iframe = urlsplit(iframe_url)
        file_values = parse_qs(parsed_iframe.query).get("file", [])
        candidates = [urljoin(iframe_url, file_value) for file_value in file_values]
        if not candidates and _looks_like_embedded_legal_document(iframe_url):
            candidates = [iframe_url]
        for candidate in candidates:
            candidate = _strip_url_fragment(candidate)
            parsed = urlsplit(candidate)
            if _url_origin(candidate) != container_origin:
                continue
            if candidate not in urls:
                urls.append(candidate)

    # The Australian Federal Register renders multi-volume legislation with
    # one iframe for the active volume and sibling links targeting that frame.
    volume_links = re.findall(
        r"<a\b(?=[^>]*\btarget\s*=\s*(['\"])epubFrame\1)[^>]*?"
        r"\bhref\s*=\s*(['\"])(.*?)\2",
        markup,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for _target_quote, _href_quote, raw_value in volume_links:
        candidate = _strip_url_fragment(
            urljoin(container_url, html_module.unescape(raw_value).strip())
        )
        parsed = urlsplit(candidate)
        if _url_origin(candidate) != container_origin:
            continue
        if not _EPUB_VOLUME_PATH_PATTERN.search(parsed.path):
            continue
        if candidate not in urls:
            urls.append(candidate)
    if (urlsplit(container_url).hostname or "").casefold() == "lom.agc.gov.my":
        # LOM pages often list the as-made Act, amendments, subsidiary
        # instruments, and a much smaller consolidated reprint. Prefer the
        # reprint so validation does not accidentally stop on an amendment.
        urls = [
            url
            for _index, url in sorted(
                enumerate(urls),
                key=lambda item: (
                    0 if "reprint" in item[1].casefold() else 1,
                    item[0],
                ),
            )
        ]
    return urls


def _strip_url_fragment(url: str) -> str:
    parsed = urlsplit(url)
    return parsed._replace(fragment="").geturl()


def _looks_like_embedded_legal_document(url: str) -> bool:
    path = urlsplit(url).path.casefold()
    return path.endswith((".pdf", ".htm", ".html")) or "/epub/" in path


def _url_origin(url: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.casefold()
        host = (parsed.hostname or "").casefold()
        if scheme not in {"http", "https"} or not host:
            return None
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError:
        return None
    return scheme, host, port


def _html_text(markup: str) -> str:
    body_match = re.search(r"<body[^>]*>(.*?)</body>", markup, re.IGNORECASE | re.DOTALL)
    raw = body_match.group(1) if body_match else markup
    raw = re.sub(r"<(script|style)\b[^>]*>.*?</\1\s*>", " ", raw, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html_module.unescape(text)).strip()


def _has_legal_signal(text: str) -> bool:
    lower = text.casefold()
    return any(
        term in lower
        for term in (
            " act ",
            " law ",
            " section ",
            " article ",
            "personal data",
            "cyber security",
            "cybersecurity",
            "个人信息",
            "网络安全",
            "พระราชบัญญัติ",
            "มาตรา",
        )
    )


def _looks_like_error_or_challenge(text: str) -> bool:
    lower = text.casefold()
    signals = (
        "404 page not found",
        "page not found",
        "access denied",
        "attention required cloudflare",
        "cf-chl-",
        "captcha",
        "verify you are human",
        "checking your browser",
        "just a moment",
    )
    return any(signal in lower for signal in signals)


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
