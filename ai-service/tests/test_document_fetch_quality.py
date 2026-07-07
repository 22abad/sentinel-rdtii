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


def test_assess_crawl_quality_flags_short_non_legal_text():
    quality = assess_crawl_quality(
        "Home About Contact Search Menu Privacy Policy Subscribe Share",
        source_url="https://www.pdpc.gov.sg/page",
    )

    assert quality.status == "weak"
    assert quality.should_extract is False
    assert quality.char_count > 0
    assert quality.legal_signal_score < 2
