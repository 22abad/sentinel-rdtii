"""Resilient legal-source fetching + pseudo-intelligent candidate triage.

This module encodes field experience won while discovering NEW laws for the
RDTII submission: *which* fetch strategy actually reaches *which* government
portal, in *what order* to try them, and how to judge — without an LLM, purely
deterministically ("pseudo-intelligence") — whether a discovered provision is
real, novel and usable.

The three reusable pieces:

1. ``SITE_HINTS`` — a registry of hard-won facts about specific portals
   (e.g. Singapore's SSO serves plain ``curl`` with a browser User-Agent but
   403s a naive fetch; Australia's Federal Register hides the text behind an
   embedded-HTML page; state portals hide it behind an *authorised PDF*; the
   NSW portal is behind a Cloudflare JS challenge that blocks all automated
   clients). Ordering the strategies by these hints turns a string of failures
   into a first-try hit.

2. ``verify_quote_at_source`` — the anti-hallucination gate for *discovery*:
   fetch the source, then confirm the claimed verbatim quote is actually a
   substring of the fetched text (whitespace-normalised). This is the check we
   applied ~15 times by hand; here it is once, reusable.

3. ``triage_candidate`` — composes fetch+verify with the existing
   ``is_known_law`` and ``_is_weak_evidence`` heuristics into a single verdict,
   so a discovery pipeline can accept/reject a candidate the same way a careful
   human would.

Everything degrades gracefully: no network / missing optional deps → an
``UNVERIFIED`` verdict, never an exception that aborts a sweep.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# ── Field-learned facts about specific portals ──────────────────────────────
# strategy names: "http_ua" (browser-UA HTTP GET, HTML stripped),
# "pdf" (download + text-extract), "browser" (heavy Playwright/OpenCLI cascade).
SITE_HINTS: dict[str, dict] = {
    "sso.agc.gov.sg": {
        "order": ["browser", "http_ua"],
        "note": "Singapore SSO went behind an AWS WAF (2026-07: the HTML endpoint now "
                "returns HTTP 202 with an empty body to curl/WebFetch). The ?ViewType=Pdf "
                "endpoint is NOT challenged, and the browser strategy's document_fetch "
                "cascade auto-falls back to it (verified 2026-07-16: full PDPA 191KB). "
                "Still request ?ProvIds=prNN- to anchor the provision. Plain http_ua is a "
                "last resort now that the WAF is live.",
    },
    "legislation.gov.au": {
        "order": ["browser"],
        "note": "AU Federal Register: plain HTTP returns a JS shell page (long enough to "
                "look 'usable' but without the statute body) — go straight to the full "
                "document_fetch cascade, which resolves the embedded HTML/EPUB body.",
    },
    "pdp.gov.my": {"order": ["pdf", "http_ua"], "note": "Malaysia PDP: Acts/standards are PDFs."},
    "lom.agc.gov.my": {"order": ["pdf", "http_ua"], "note": "Malaysia AGC: statute PDFs."},
    "mcmc.gov.my": {"order": ["pdf"], "note": "MCMC: Act PDFs."},
    "legislation.vic.gov.au": {
        "order": ["pdf", "browser"],
        "note": "VIC: the /in-force/acts/... page is only a version-history table; the text "
                "is in the authorised PDF at content.legislation.vic.gov.au/.../*-authorised.pdf.",
    },
    "legislation.nt.gov.au": {
        "order": ["pdf", "browser"],
        "note": "NT: landing page is a version table; real text at /api/sitecore/Act/PDF?id=NNNN.",
    },
    "legislation.nsw.gov.au": {
        "order": ["browser"],
        "note": "NSW: Cloudflare blocks plain HTTP / curl / WebFetch — but the project's "
                "Playwright browser fallback gets through (verified 2026-07-16, s19(2) "
                "captured verbatim). Use the browser strategy; only if that also fails, "
                "tell the user a manual browser is needed.",
    },
    "oaic.gov.au": {"order": ["pdf", "http_ua"], "note": "OAIC guidance PDFs are reachable."},
}

_DEFAULT_ORDER = ["http_ua", "pdf", "browser"]
_MIN_USABLE_LEN = 400


class Verdict(str, Enum):
    PROMOTE = "PROMOTE"            # verified verbatim + novel + strong
    REJECT_KNOWN = "REJECT_KNOWN"  # already in the KNOWN baseline
    REJECT_WEAK = "REJECT_WEAK"    # quote is a fragment / bare title on a non-framework indicator
    UNVERIFIED = "UNVERIFIED"      # could not confirm the quote at the official source


@dataclass
class FetchOutcome:
    url: str
    text: str | None = None
    method: str | None = None          # which strategy succeeded
    tried: list[str] = field(default_factory=list)
    blocked: bool = False              # a known-blocked portal (needs a human browser)
    note: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.text and len(self.text) >= _MIN_USABLE_LEN)


@dataclass
class QuoteVerdict:
    found: bool
    method: str | None = None
    url: str = ""
    blocked: bool = False
    detail: str = ""


@dataclass
class CandidateVerdict:
    verdict: Verdict
    quote_found: bool
    is_known: bool
    is_weak: bool
    fetch_method: str | None = None
    detail: str = ""


# ── normalisation helpers ───────────────────────────────────────────────────
def _normalize(text: str) -> str:
    """Collapse all runs of whitespace to single spaces so a copy that differs
    only in line-wrapping / indentation still matches."""
    return re.sub(r"\s+", " ", (text or "")).strip()


def _strip_html(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", markup)
    return re.sub(r"(?s)<[^>]+>", " ", markup)


def _domain(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().lstrip("www.")
    except Exception:  # noqa: BLE001
        return ""


def strategy_order(url: str) -> tuple[list[str], dict]:
    """Return the strategy order for a URL plus its site-hint dict.

    A domain listed in SITE_HINTS uses its curated order; otherwise the default
    cascade. A URL that points at a PDF is always tried as a PDF first — even on
    a browser-only domain — because a curl+UA download beats a Playwright render
    of a JS shell. (legislation.gov.au serves the real statute body only via its
    ``/text/original/pdf`` endpoint; the HTML routes return a JS shell.)"""
    host = _domain(url)
    hint = {}
    for dom, h in SITE_HINTS.items():
        if host == dom or host.endswith("." + dom):
            hint = h
            break
    if hint.get("blocked"):
        return [], hint
    order = list(hint.get("order") or _DEFAULT_ORDER)
    # A PDF endpoint may end in ".pdf" or in a trailing "/pdf" path segment
    # (Australia's Federal Register uses ".../text/original/pdf"). Force the pdf
    # strategy to the front regardless of the site hint — a PDF URL is a PDF.
    low = url.lower()
    path = low.split("?")[0].rstrip("/")
    # Also a ?ViewType=Pdf query (Singapore SSO's un-WAF'd PDF endpoint) is a PDF:
    # Playwright can't render it (it triggers a download), but curl+UA + pdftotext
    # gets the real statute body.
    if path.endswith(".pdf") or path.endswith("/pdf") or "viewtype=pdf" in low:
        order = ["pdf"] + [s for s in order if s != "pdf"]
    return order, hint


# ── fetch strategies ────────────────────────────────────────────────────────
def _fetch_http_ua(url: str, timeout: float = 30.0) -> str | None:
    try:
        import httpx

        with httpx.Client(follow_redirects=True, timeout=timeout,
                          headers={"User-Agent": _BROWSER_UA}) as client:
            resp = client.get(url)
        if resp.status_code != 200:
            return None
        ctype = resp.headers.get("content-type", "")
        if "pdf" in ctype.lower():
            return None  # let the pdf strategy handle it
        return _strip_html(resp.text)
    except Exception:  # noqa: BLE001
        return None


def _fetch_pdf(url: str, timeout: float = 60.0) -> str | None:
    try:
        import hashlib
        import tempfile
        from pathlib import Path

        import httpx

        with httpx.Client(follow_redirects=True, timeout=timeout,
                          headers={"User-Agent": _BROWSER_UA}) as client:
            resp = client.get(url)
        if resp.status_code != 200 or not resp.content:
            return None
        digest = hashlib.sha256(resp.content).hexdigest()[:16]
        tmp = Path(tempfile.gettempdir()) / f"srcverify-{digest}.pdf"
        tmp.write_bytes(resp.content)
        try:
            from services.canvas_file_ingest import _extract_text

            return _extract_text(str(tmp), tmp.name)
        finally:
            try:
                tmp.unlink()
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        return None


def _fetch_browser(url: str, timeout: float = 120.0) -> str | None:
    """Last-resort strategy: the project's full fetch cascade (Playwright
    browser included). Gets through Cloudflare-style JS challenges that block
    plain HTTP — proven on legislation.nsw.gov.au. Sync wrapper; returns None
    inside a running event loop (callers there should await document_fetch
    directly)."""
    try:
        import asyncio

        try:
            asyncio.get_running_loop()
            return None  # can't nest asyncio.run — async callers go direct
        except RuntimeError:
            pass
        from services.document_fetch import fetch_document_text

        doc = asyncio.run(
            asyncio.wait_for(fetch_document_text(url, browser_mode="auto"), timeout=timeout)
        )
        return getattr(doc, "text", None)
    except Exception:  # noqa: BLE001
        return None


_STRATEGY_FUNCS = {"http_ua": _fetch_http_ua, "pdf": _fetch_pdf, "browser": _fetch_browser}


def fetch_text_resilient(url: str, *, order: list[str] | None = None) -> FetchOutcome:
    """Try fetch strategies in the site-appropriate order until one returns
    usable text. Never raises. When every strategy fails, the outcome carries a
    human-readable ``note`` explaining what was tried and what the user should
    do — a blocked portal must be REPORTED, never silently skipped."""
    strategies, hint = strategy_order(url)
    if hint.get("blocked"):
        return FetchOutcome(url=url, blocked=True, note=hint.get("note", ""))
    if order is not None:
        strategies = order

    outcome = FetchOutcome(url=url, note=hint.get("note", ""))
    for name in strategies:
        fn = _STRATEGY_FUNCS.get(name)
        if fn is None:
            continue
        outcome.tried.append(name)
        text = fn(url)
        if text and len(text) >= _MIN_USABLE_LEN:
            outcome.text = text
            outcome.method = name
            return outcome
    # All strategies failed — tell the user, loudly and specifically.
    tried = ", ".join(outcome.tried) or "none"
    outcome.note = (
        f"Could not fetch {url} (tried: {tried}). The portal may block automated "
        f"clients — open it in a regular browser and verify manually. "
        + (hint.get("note", "") and f"Site note: {hint['note']}")
    ).strip()
    return outcome


# ── pseudo-intelligence: verify + triage ────────────────────────────────────
def verify_quote_at_source(quote: str, url: str, *, fetch=fetch_text_resilient) -> QuoteVerdict:
    """Confirm ``quote`` appears verbatim (whitespace-normalised) at ``url``.

    This is the discovery anti-hallucination gate: a candidate whose quote we
    cannot locate at its own official source is UNVERIFIED, no matter how
    plausible it looks."""
    q = _normalize(quote)
    if len(q) < 12:
        return QuoteVerdict(found=False, url=url, detail="quote too short to verify")
    outcome = fetch(url)
    if outcome.blocked:
        return QuoteVerdict(found=False, url=url, blocked=True,
                            detail="portal blocks automated clients — verify in a browser")
    if not outcome.ok:
        # Surface the full failure note — the user must be told why the crawl
        # failed and what to do (e.g. open the portal in a regular browser).
        return QuoteVerdict(found=False, url=url, detail=outcome.note or "could not fetch usable text")
    found = q in _normalize(outcome.text)
    return QuoteVerdict(found=found, method=outcome.method, url=url,
                        detail="verbatim match" if found else "quote not present in fetched text")


def triage_candidate(
    economy: str,
    law_name: str,
    quote: str,
    url: str,
    *,
    indicator_id: str = "",
    known_index=None,
    verify: bool = True,
) -> CandidateVerdict:
    """Run the full deterministic gate a careful human would: is the quote real
    at the source, is the law already KNOWN, and is the quote strong enough to
    stand as evidence. Returns a single verdict.

    ``known_index`` defaults to the project's unioned KNOWN inventory. Set
    ``verify=False`` to skip the network step (novelty + strength only)."""
    # Novelty (reuse the existing baseline gate).
    is_known = False
    try:
        from submission.novelty import is_known_law, known_law_index

        idx = known_index if known_index is not None else known_law_index()
        is_known = is_known_law(economy, law_name, idx)
    except Exception:  # noqa: BLE001
        pass

    # Evidence strength (reuse the submission noise-gate rule).
    is_weak = False
    try:
        from submission.schema import _is_weak_evidence

        is_weak = _is_weak_evidence(law_name, quote, indicator_id)
    except Exception:  # noqa: BLE001
        pass

    # Short-circuit: a candidate that's already KNOWN or WEAK is rejected without
    # spending a network round-trip to verify a quote we won't use anyway.
    if is_known:
        return CandidateVerdict(Verdict.REJECT_KNOWN, False, True, is_weak,
                                detail="already in the KNOWN baseline")
    if is_weak:
        return CandidateVerdict(Verdict.REJECT_WEAK, False, False, True,
                                detail="quote is a fragment or a bare title on a non-framework indicator")

    quote_found = False
    fetch_method = None
    detail = ""
    if verify:
        qv = verify_quote_at_source(quote, url)
        quote_found = qv.found
        fetch_method = qv.method
        detail = qv.detail

    if verify and not quote_found:
        verdict = Verdict.UNVERIFIED
    else:
        verdict = Verdict.PROMOTE
    return CandidateVerdict(
        verdict=verdict, quote_found=quote_found, is_known=is_known,
        is_weak=is_weak, fetch_method=fetch_method, detail=detail,
    )
