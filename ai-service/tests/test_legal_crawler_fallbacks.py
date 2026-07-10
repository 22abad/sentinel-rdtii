from __future__ import annotations

import ssl
from types import SimpleNamespace

import pytest

from legal_crawler.fallbacks import (
    _embedded_document_urls,
    _http_pdf_response_result,
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
