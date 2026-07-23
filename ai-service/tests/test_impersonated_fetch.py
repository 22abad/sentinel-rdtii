"""Tests for the curl_cffi impersonated fetch rung + SSO print-endpoint rewrite."""

from __future__ import annotations

from legal_crawler.fallbacks import _html_to_legal_text, _sso_print_url


class TestSsoPrintUrl:
    def test_act_page_rewritten_to_print_endpoint(self):
        # The plain /Act page lazy-loads provisions and yields a ~1/8 shell;
        # the print endpoint server-renders the full body.
        out = _sso_print_url("https://sso.agc.gov.sg/Act/PDPA2012")
        assert out == (
            "https://sso.agc.gov.sg/Act/PDPA2012"
            "?ViewType=Print&PrintType=html&ProvIds=all-."
        )

    def test_subsidiary_legislation_also_rewritten(self):
        out = _sso_print_url("https://sso.agc.gov.sg/SL/PDPA2012-S63-2021")
        assert "ViewType=Print" in out and out.startswith(
            "https://sso.agc.gov.sg/SL/PDPA2012-S63-2021?"
        )

    def test_already_a_print_or_pdf_view_is_left_alone(self):
        pdf = "https://sso.agc.gov.sg/Act/PDPA2012?ViewType=Pdf"
        assert _sso_print_url(pdf) == pdf

    def test_non_sso_host_is_untouched(self):
        au = "https://www.legislation.gov.au/C2004A00025/latest/text"
        assert _sso_print_url(au) == au

    def test_sso_non_act_path_untouched(self):
        # A search/browse page is not a statute — don't rewrite it.
        browse = "https://sso.agc.gov.sg/Browse/Act/Current"
        assert _sso_print_url(browse) == browse


class TestHtmlToLegalText:
    def test_strips_scripts_styles_and_tags(self):
        html = (
            "<body><script>var x=1;</script><style>.a{}</style>"
            "<p>An organisation must cease to retain personal data.</p></body>"
        )
        text = _html_to_legal_text(html)
        assert "cease to retain personal data" in text
        assert "var x" not in text and ".a{}" not in text

    def test_prefers_sso_legis_container(self):
        html = (
            '<body><nav>menu junk</nav>'
            '<div class="legis"><p>Section 25. Retention of personal data.</p>'
            "</div></div></div></body>"
        )
        text = _html_to_legal_text(html)
        assert "Retention of personal data" in text


class TestBodyIntegrityGate:
    def test_rejects_short_content(self):
        from legal_crawler.fallbacks import _is_real_legal_content
        assert not _is_real_legal_content("Personal Data Protection Act")  # < min_chars

    def test_rejects_waf_banner_and_challenge(self):
        from legal_crawler.fallbacks import _is_real_legal_content
        banner = "Just a moment... checking your browser. " * 20
        assert not _is_real_legal_content(banner)

    def test_rejects_nav_shell_without_legal_signal(self):
        from legal_crawler.fallbacks import _is_real_legal_content
        shell = "Home About Contact Login Menu Search Sitemap Privacy Terms " * 30
        assert not _is_real_legal_content(shell)

    def test_accepts_real_statute_body(self):
        from legal_crawler.fallbacks import _is_real_legal_content
        body = (
            "Personal Data Protection Act 2012. Section 25. An organisation must "
            "cease to retain its documents containing personal data as soon as it "
            "is reasonable to assume the purpose is no longer served. " * 6
        )
        assert _is_real_legal_content(body)

    def test_none_and_empty_are_not_real(self):
        from legal_crawler.fallbacks import _is_real_legal_content
        assert not _is_real_legal_content(None)
        assert not _is_real_legal_content("")
