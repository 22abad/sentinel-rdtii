"""Tests for the resilient-fetch + pseudo-intelligent triage module.

Hermetic: the network layer is monkeypatched, so these exercise the strategy
ordering, the verbatim gate, and the composed verdict without hitting a portal.
"""

from __future__ import annotations

import services.source_verification as sv
from services.source_verification import (
    CandidateVerdict,
    FetchOutcome,
    QuoteVerdict,
    Verdict,
    strategy_order,
    triage_candidate,
    verify_quote_at_source,
)

_PROVISION = (
    "Customer information must not, in any way, be disclosed by a bank in "
    "Singapore or any of its officers to any other person except as expressly "
    "provided in this Act."
)


def test_strategy_order_uses_site_hints():
    sso, _ = strategy_order("https://sso.agc.gov.sg/Act/BA1970?ProvIds=pr47-")
    assert sso == ["http_ua"]  # SSO: curl+UA only
    vic, hint = strategy_order("https://www.legislation.vic.gov.au/in-force/acts/x")
    assert vic[0] == "pdf"  # VIC text lives in the authorised PDF
    # A .pdf URL is always tried as a PDF first, whatever the domain.
    order, _ = strategy_order("https://example.gov/some/act.pdf")
    assert order[0] == "pdf"


def test_nsw_is_marked_blocked():
    order, hint = strategy_order("https://legislation.nsw.gov.au/view/whole/html/act-1998-133")
    assert order == [] and hint.get("blocked") is True
    outcome = sv.fetch_text_resilient("https://legislation.nsw.gov.au/view/whole/html/act-1998-133")
    assert outcome.blocked is True and not outcome.ok


def test_verify_quote_found_when_present(monkeypatch):
    # A fetch that returns the provision (with different line-wrapping) still matches.
    wrapped = _PROVISION.replace(" ", "\n   ")

    def fake_fetch(url, **kw):
        body = ("lorem ipsum preamble " * 40) + wrapped + (" tail matter " * 40)
        return FetchOutcome(url=url, text=body, method="http_ua")

    qv = verify_quote_at_source(_PROVISION, "https://sso.agc.gov.sg/Act/BA1970", fetch=fake_fetch)
    assert qv.found is True and qv.method == "http_ua"


def test_verify_quote_absent(monkeypatch):
    def fake_fetch(url, **kw):
        return FetchOutcome(url=url, text="a" * 500, method="http_ua")

    qv = verify_quote_at_source(_PROVISION, "https://sso.agc.gov.sg/x", fetch=fake_fetch)
    assert qv.found is False


def test_verify_reports_blocked_portal():
    qv = verify_quote_at_source(_PROVISION, "https://legislation.nsw.gov.au/view/act-1998-133")
    assert qv.found is False and qv.blocked is True


def test_triage_rejects_known_law(monkeypatch):
    # A clearly-known SGP law -> REJECT_KNOWN, and we never bother fetching.
    monkeypatch.setattr(sv, "verify_quote_at_source",
                        lambda *a, **k: QuoteVerdict(found=True, method="http_ua"))
    v = triage_candidate("SGP", "Personal Data Protection Act 2012", _PROVISION,
                         "https://sso.agc.gov.sg/Act/PDPA2012", indicator_id="P7-I1")
    assert v.verdict == Verdict.REJECT_KNOWN and v.is_known is True


def test_triage_rejects_weak_quote(monkeypatch):
    monkeypatch.setattr(sv, "verify_quote_at_source",
                        lambda *a, **k: QuoteVerdict(found=True))
    # A bare title-quote on a non-framework indicator is weak evidence.
    v = triage_candidate("SGP", "Some Brand New Data Act 2025", "Some Brand New Data Act 2025",
                         "https://sso.agc.gov.sg/Act/x", indicator_id="P7-I5")
    assert v.verdict == Verdict.REJECT_WEAK and v.is_weak is True


def test_triage_promotes_verified_novel_strong(monkeypatch):
    monkeypatch.setattr(sv, "verify_quote_at_source",
                        lambda *a, **k: QuoteVerdict(found=True, method="pdf"))
    v = triage_candidate("AUS", "Some Genuinely New Privacy Instrument 2025", _PROVISION,
                         "https://example.gov.au/x.pdf", indicator_id="P7-I1")
    assert v.verdict == Verdict.PROMOTE
    assert v.quote_found and not v.is_known and not v.is_weak


def test_triage_unverified_when_quote_absent(monkeypatch):
    monkeypatch.setattr(sv, "verify_quote_at_source",
                        lambda *a, **k: QuoteVerdict(found=False, detail="not present"))
    v = triage_candidate("AUS", "Some Genuinely New Privacy Instrument 2025", _PROVISION,
                         "https://example.gov.au/x", indicator_id="P7-I1")
    assert v.verdict == Verdict.UNVERIFIED and v.quote_found is False
