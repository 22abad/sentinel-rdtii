from __future__ import annotations

import pytest

from services.document_fetch import assess_crawl_quality, fetch_document_text


@pytest.mark.anyio
async def test_fetch_document_text_returns_good_crawl_quality(monkeypatch):
    legal_text = (
        "Personal Data Protection Act 2012 Section 26 requires organisations "
        "to comply with data protection obligations and cross-border transfer "
        "requirements. " * 20
    )

    async def fake_fetch(_url: str, browser_mode: str = "auto"):
        return {
            "type": "text",
            "url": "https://sso.agc.gov.sg/Act/PDPA2012",
            "text": legal_text,
            "metadata": {
                "source": "opencli",
                "title": "Personal Data Protection Act 2012",
                "total_chars": len(legal_text),
            },
        }

    monkeypatch.setattr("crawler.fetch_legal_content", fake_fetch)

    document = await fetch_document_text("https://sso.agc.gov.sg/Act/PDPA2012", browser_mode="opencli")

    assert document.quality.status == "good"
    assert document.quality.should_extract is True
    assert document.quality.legal_signal_score >= 2
    assert document.crawl_metadata["fetch_method"] == "opencli"
    assert document.crawl_metadata["title"] == "Personal Data Protection Act 2012"


@pytest.mark.anyio
async def test_fetch_document_text_flags_error_page(monkeypatch):
    async def fake_fetch(_url: str, browser_mode: str = "auto"):
        return {
            "type": "text",
            "text": "Page Not Found. The page you are looking for may have been removed.",
            "metadata": {"source": "playwright"},
        }

    monkeypatch.setattr("crawler.fetch_legal_content", fake_fetch)

    document = await fetch_document_text("https://www.imda.gov.sg/missing")

    assert document.quality.status == "error_page"
    assert document.quality.should_extract is False
    assert any("error" in warning for warning in document.quality.warnings)


@pytest.mark.anyio
async def test_fetch_document_text_preserves_http_pdf_audit_metadata(monkeypatch):
    pdf_metadata = {
        "ocr_ratio": 0.5,
        "pdf_type": "mixed",
        "page_char_spans": [{"page": 1, "start": 0, "end": 900}],
        "source_file_sha256": "a" * 64,
    }

    async def fake_fetch(_url: str, browser_mode: str = "auto"):
        return {
            "type": "text",
            "url": "https://official.example/law",
            "text": "Section 1 personal data law shall apply. " * 30,
            "pdf_metadata": pdf_metadata,
            "metadata": {"source": "http_fallback_pdf", "original_format": "pdf"},
        }

    monkeypatch.setattr("crawler.fetch_legal_content", fake_fetch)
    document = await fetch_document_text("https://official.example/law")

    assert document.content_type == "pdf"
    assert document.pdf_metadata == pdf_metadata


def test_assess_crawl_quality_flags_short_non_legal_text():
    quality = assess_crawl_quality(
        "Home About Contact Search Menu Privacy Policy Subscribe Share",
        source_url="https://www.pdpc.gov.sg/page",
    )

    assert quality.status == "weak"
    assert quality.should_extract is False
    assert quality.char_count > 0
    assert quality.legal_signal_score < 2


def test_assess_crawl_quality_recognizes_chinese_statute_text():
    quality = assess_crawl_quality(
        "中华人民共和国个人信息保护法 第一条 为了保护个人信息权益，规范个人信息处理活动。"
        "个人信息处理者应当遵守法律规定。" * 30,
        source_url="https://flk.npc.gov.cn/detail?id=law",
    )

    assert quality.status == "good"
    assert quality.should_extract is True
    assert quality.legal_signal_score >= 2
