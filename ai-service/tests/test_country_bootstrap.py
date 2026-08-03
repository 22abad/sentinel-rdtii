"""G1 gate — unit tests for the Country Bootstrap module (all mocked).

S3-1 rule: the engine must onboard an UNSEEN country autonomously. The
hold-out ground truth (data/holdout/) is for tests/eval only — the engine
importing or reading it is cheating, and there is a static check for that.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Anti-cheat: engine code must never touch the hold-out ground truth
# ---------------------------------------------------------------------------

def test_bootstrap_module_never_references_holdout_ground_truth():
    src = Path(__file__).resolve().parents[1] / "discovery" / "bootstrap.py"
    text = src.read_text(encoding="utf-8").lower()
    for marker in ("data/holdout", "holdout_countries", "vbpl.vn", "adilet.zan",
                   "laws.gov.fj", "agc.gov.bn", "mptc.gov.kh"):
        assert marker not in text, (
            f"discovery/bootstrap.py references hold-out ground truth ({marker!r}) — "
            "the engine must discover portals autonomously"
        )


# ---------------------------------------------------------------------------
# Country resolution (static world table, no network)
# ---------------------------------------------------------------------------

def test_resolve_country_unseen_countries():
    from discovery.bootstrap import resolve_country

    p = resolve_country("Vietnam")
    assert p.iso3 == "VNM" and "vi" in p.languages

    p = resolve_country("kazakhstan")
    assert p.iso3 == "KAZ" and {"kk", "ru"} & set(p.languages)

    p = resolve_country("Brunei Darussalam")
    assert p.iso3 == "BRN"

    p = resolve_country("Fiji")
    assert p.iso3 == "FJI" and "en" in p.languages


def test_resolve_country_known_economies_pass_through():
    from discovery.bootstrap import resolve_country

    # already-registered economies resolve consistently with submission.schema
    assert resolve_country("Mongolia").iso3 == "MNG"
    assert resolve_country("Timor-Leste").iso3 == "TLS"


def test_resolve_country_unknown_raises_clearly():
    from discovery.bootstrap import resolve_country

    with pytest.raises(ValueError):
        resolve_country("Atlantis")


# ---------------------------------------------------------------------------
# Official-domain scoring heuristic
# ---------------------------------------------------------------------------

def test_score_domain_prefers_government_domains():
    from discovery.bootstrap import resolve_country, score_domain

    vnm = resolve_country("Vietnam")
    khm = resolve_country("Cambodia")

    # ccTLD gov patterns beat commercial sites
    assert score_domain("moj.gov.vn", vnm) > score_domain("linkedin.com", vnm)
    assert score_domain("mptc.gov.kh", khm) > score_domain("news.com.kh", khm)
    # bare ccTLD official-ish legal portal still scores above foreign .com
    assert score_domain("vbpl.vn", vnm) > score_domain("lexology.com", vnm)
    # third-party legal aggregators are explicitly penalized
    assert score_domain("lexology.com", vnm) < 0
    assert score_domain("dataguidance.com", vnm) < 0


def test_score_domain_wrong_country_cctld_is_not_official():
    from discovery.bootstrap import resolve_country, score_domain

    vnm = resolve_country("Vietnam")
    assert score_domain("legalinfo.mn", vnm) <= 0  # Mongolian portal, wrong country


# ---------------------------------------------------------------------------
# Portal discovery (search + reachability fully mocked)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_discover_official_sources_ranks_and_filters(monkeypatch):
    from discovery.bootstrap import discover_official_sources, resolve_country

    vnm = resolve_country("Vietnam")

    async def fake_search(query: str, limit: int = 10):
        return [
            {"title": "Văn bản pháp luật — CSDL quốc gia", "url": "https://vbpl.vn/pages/portal.aspx"},
            {"title": "Vietnam Data Protection — Lexology", "url": "https://www.lexology.com/vn"},
            {"title": "Ministry of Justice", "url": "https://moj.gov.vn/Pages/home.aspx"},
            {"title": "Some blog", "url": "https://vietnamlawblog.com/x"},
        ]

    async def fake_reachable(url: str) -> bool:
        return "vbpl.vn" in url or "moj.gov.vn" in url

    monkeypatch.setattr("discovery.bootstrap._url_reachable", fake_reachable)

    sources = await discover_official_sources(vnm, search_fn=fake_search)

    domains = [d for s in sources for d in s.domains]
    assert "vbpl.vn" in domains and "moj.gov.vn" in domains
    assert all("lexology.com" not in d for d in domains)
    assert all("vietnamlawblog.com" not in d for d in domains)
    for s in sources:
        assert s.country_code == "VNM"
        assert s.source_grade == "primary"


# ---------------------------------------------------------------------------
# Query localization (LLM mocked, cache verified)
# ---------------------------------------------------------------------------

def test_localize_queries_caches_and_reuses(tmp_path, monkeypatch):
    from discovery.bootstrap import localize_queries, resolve_country

    vnm = resolve_country("Vietnam")
    calls = {"n": 0}

    class FakeProvider:
        def query(self, prompt: str, system: str = "") -> str:
            calls["n"] += 1
            return json.dumps({
                "personal data protection": "bảo vệ dữ liệu cá nhân",
                "cybersecurity": "an ninh mạng",
            })

    monkeypatch.setattr("discovery.bootstrap._CACHE_DIR", tmp_path)

    t1 = localize_queries(vnm, ["personal data protection", "cybersecurity"], FakeProvider())
    assert t1["personal data protection"] == "bảo vệ dữ liệu cá nhân"
    assert calls["n"] == 1

    t2 = localize_queries(vnm, ["personal data protection", "cybersecurity"], FakeProvider())
    assert t2 == t1
    assert calls["n"] == 1  # cache hit — provider not called again
    assert (tmp_path / "VNM.json").exists()


# ---------------------------------------------------------------------------
# Dynamic economy registration
# ---------------------------------------------------------------------------

def test_register_dynamic_economy_wires_economy_code():
    from discovery.bootstrap import register_dynamic_economy
    from submission.schema import economy_code, economy_display_name

    register_dynamic_economy("VNM", "Vietnam")
    assert economy_code("Vietnam") == "VNM"
    assert economy_code("VNM") == "VNM"
    assert economy_display_name("VNM") == "Vietnam"


# ---------------------------------------------------------------------------
# Orchestrator (everything mocked)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_bootstrap_country_end_to_end_mocked(tmp_path, monkeypatch):
    from discovery.bootstrap import bootstrap_country

    async def fake_search(query: str, limit: int = 10):
        return [{"title": "Fiji Laws", "url": "https://laws.gov.fj/Acts"}]

    async def fake_reachable(url: str) -> bool:
        return True

    monkeypatch.setattr("discovery.bootstrap._url_reachable", fake_reachable)
    monkeypatch.setattr("discovery.bootstrap._CACHE_DIR", tmp_path)

    result = await bootstrap_country("Fiji", search_fn=fake_search, provider=None)

    assert result.profile.iso3 == "FJI"
    assert result.sources and "laws.gov.fj" in result.sources[0].domains
    # English-language country needs no translation pass
    assert result.localized_terms == {}
    from submission.schema import economy_code
    assert economy_code("Fiji") == "FJI"
