from __future__ import annotations

import asyncio
import ssl
from types import SimpleNamespace

import pytest

from legal_crawler.fallbacks import (
    _embedded_document_urls,
    _http_pdf_response_result,
    _try_embedded_document,
    _try_http_fallback,
)
from legal_crawler.constants import _SSL_CTX


def test_crawler_ssl_context_verifies_certificates_and_hostnames():
    assert _SSL_CTX.verify_mode == ssl.CERT_REQUIRED
    assert _SSL_CTX.check_hostname is True


def test_embedded_document_urls_extracts_same_origin_pdf_viewer_file():
    markup = """
    <iframe
      data-src="pdfjs/web/viewer.html?file=../../../ilims/upload/portal/akta/LOM/EN/Act%20709.pdf&amp;embedded=true"
    ></iframe>
    """

    urls = _embedded_document_urls(
        markup,
        "https://lom.agc.gov.my/act-detail.php?act=709&lang=BI&type=principal",
    )

    assert urls == [
        "https://lom.agc.gov.my/ilims/upload/portal/akta/LOM/EN/Act 709.pdf"
    ]


def test_embedded_document_urls_prefer_lom_consolidated_reprint():
    markup = """
    <iframe data-src="pdfjs/web/viewer.html?file=../../../laws/Act%20562%20Original.pdf"></iframe>
    <iframe data-src="pdfjs/web/viewer.html?file=../../../laws/Act%20A1121.pdf"></iframe>
    <iframe data-src="pdfjs/web/viewer.html?file=../../../laws/Act%20562%20Reprint%202006.pdf"></iframe>
    """

    urls = _embedded_document_urls(
        markup,
        "https://lom.agc.gov.my/act-detail.php?act=562&lang=BI",
    )

    assert urls[0].endswith("Act 562 Reprint 2006.pdf")


def test_embedded_document_urls_extracts_australian_epub_iframe():
    document_url = (
        "https://www.legislation.gov.au/C2024A00098/asmade/2024-11-29/"
        "text/2/epub/OEBPS/document_1/document_1.html"
    )
    markup = f'<iframe title="Document" src="{document_url}"></iframe>'

    assert _embedded_document_urls(
        markup,
        "https://www.legislation.gov.au/C2024A00098/latest/text",
    ) == [document_url]


def test_embedded_document_urls_extracts_all_australian_epub_volumes():
    base = (
        "https://www.legislation.gov.au/C2004A02124/2026-06-04/2026-06-04/"
        "text/original/epub/OEBPS"
    )
    volume_1 = f"{base}/document_1/document_1.html"
    volume_2 = f"{base}/document_2/document_2.html"
    markup = f"""
    <iframe title="Document" src="{volume_1}#active-section"></iframe>
    <a href="{volume_1}#section-1" target="epubFrame">Volume 1</a>
    <a target="epubFrame" href="{volume_2}">Volume 2</a>
    """

    assert _embedded_document_urls(
        markup,
        "https://www.legislation.gov.au/C2004A02124/latest/text",
    ) == [volume_1, volume_2]


@pytest.mark.anyio
async def test_embedded_document_fetch_combines_multiple_html_volumes():
    base = "https://official.example/text/epub/OEBPS"
    volume_1 = f"{base}/document_1/document_1.html"
    volume_2 = f"{base}/document_2/document_2.html"
    markup = f"""
    <iframe src="{volume_1}"></iframe>
    <a href="{volume_1}" target="epubFrame">Volume 1</a>
    <a href="{volume_2}" target="epubFrame">Volume 2</a>
    """

    class Response:
        headers = {"content-type": "text/html"}
        content = b""
        status_code = 200

        def __init__(self, url: str, text: str):
            self.url = url
            self.text = text

        def raise_for_status(self):
            return None

    class Client:
        active = 0
        max_active = 0

        async def get(self, url: str):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0)
            try:
                label = "Volume One" if "document_1" in url else "Volume Two"
                return Response(
                    url,
                    f"<html><body>{label} Act section personal data law "
                    + ("provision " * 100)
                    + "</body></html>",
                )
            finally:
                self.active -= 1

    client = Client()
    result = await _try_embedded_document(
        client,
        markup=markup,
        container_url="https://official.example/act",
    )

    assert result is not None
    assert "Volume One" in result["text"]
    assert "Volume Two" in result["text"]
    assert result["metadata"]["embedded_document_count"] == 2
    assert result["metadata"]["embedded_document_urls"] == [volume_1, volume_2]
    assert result["metadata"]["embedded_document_http_statuses"] == [200, 200]
    assert result["metadata"]["embedded_document_origin_domains"] == ["official.example"]
    assert client.max_active == 2


@pytest.mark.anyio
async def test_embedded_document_fetch_does_not_merge_unrelated_iframes():
    first = "https://official.example/first-law.html"
    second = "https://official.example/second-law.html"
    markup = f'<iframe src="{first}"></iframe><iframe src="{second}"></iframe>'
    requested: list[str] = []

    class Response:
        headers = {"content-type": "text/html"}
        content = b""
        status_code = 200

        def __init__(self, url: str):
            self.url = url
            self.text = (
                "<html><body>First Act section personal data law "
                + ("provision " * 100)
                + "</body></html>"
            )

        def raise_for_status(self):
            return None

    class Client:
        async def get(self, url: str):
            requested.append(url)
            return Response(url)

    result = await _try_embedded_document(
        Client(),
        markup=markup,
        container_url="https://official.example/act",
    )

    assert result is not None
    assert requested == [first]
    assert result["metadata"]["embedded_document_count"] == 1


def test_embedded_document_urls_rejects_cross_origin_iframe():
    markup = '<iframe src="https://evil.example/fake-law.pdf"></iframe>'

    assert _embedded_document_urls(markup, "https://official.example/law") == []


def test_embedded_document_urls_rejects_scheme_or_port_changes():
    markup = """
    <iframe src="http://official.example/law.pdf"></iframe>
    <iframe src="https://official.example:8443/law.pdf"></iframe>
    """

    assert _embedded_document_urls(markup, "https://official.example/law") == []


@pytest.mark.anyio
async def test_http_pdf_response_detects_pdf_without_filename_suffix(monkeypatch):
    response = SimpleNamespace(
        headers={"content-type": "application/octet-stream"},
        content=b"%PDF-fake",
        url="https://www.ocs.go.th/download/opaque-id",
        status_code=200,
    )
    monkeypatch.setattr(
        "pdf_reader.read_pdf",
        lambda *_args, **_kwargs: SimpleNamespace(
            pages=["พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล มาตรา 1 " * 40],
        ),
    )

    result = await _http_pdf_response_result(
        response,
        source_url=str(response.url),
        fetch_method="http_fallback_pdf",
    )

    assert result is not None
    assert result["metadata"]["source"] == "http_fallback_pdf"
    assert result["metadata"]["tls_verified"] is True


@pytest.mark.anyio
async def test_http_fallback_uses_async_client_with_normal_tls_verification(monkeypatch):
    captured_kwargs: dict = {}
    markup = "<html><body>Privacy Act section personal data law " + ("provision " * 150) + "</body></html>"

    class Response:
        headers = {"content-type": "text/html"}
        content = markup.encode()
        text = markup
        url = "https://official.example/act"
        status_code = 200

        def raise_for_status(self):
            return None

    class AsyncClient:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr("httpx.AsyncClient", AsyncClient)

    result = await _try_http_fallback("https://official.example/act")

    assert result is not None
    assert "verify" not in captured_kwargs
    assert result["metadata"]["tls_verified"] is True


@pytest.mark.anyio
async def test_http_fallback_rejects_long_challenge_page_with_legal_keywords(monkeypatch):
    markup = (
        "<html><body>Access denied. Verify you are human. Privacy Act personal data law "
        + ("challenge " * 180)
        + "</body></html>"
    )

    class Response:
        headers = {"content-type": "text/html"}
        content = markup.encode()
        text = markup
        url = "https://official.example/act"
        status_code = 200

        def raise_for_status(self):
            return None

    class AsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr("httpx.AsyncClient", AsyncClient)

    assert await _try_http_fallback("https://official.example/act") is None
