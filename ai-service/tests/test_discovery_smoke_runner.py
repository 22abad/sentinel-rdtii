from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from discovery.schemas import LegalCandidate, LegalSourceConfig


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "discovery_smoke.py"
SPEC = importlib.util.spec_from_file_location("discovery_smoke_runner", SCRIPT_PATH)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


def test_smoke_case_filters_support_country_and_indicator():
    args = smoke.parse_args(["--countries", "SGP,MYS", "--indicators", "7.2"])

    cases = smoke.select_cases(args)

    assert [case.case_id for case in cases] == ["mys-cyber-7.2", "sgp-cyber-7.2"]


def test_smoke_candidate_acceptance_requires_live_verified_official_document():
    case = next(case for case in smoke.SMOKE_CASES if case.case_id == "sgp-privacy-7.1")
    source = LegalSourceConfig(
        name="Singapore Statutes Online",
        base_url="https://sso.agc.gov.sg",
        domains=["sso.agc.gov.sg"],
        adapter="singapore_sso",
    )
    candidate = LegalCandidate(
        id="pdpa",
        country_code="SGP",
        title="Personal Data Protection Act 2012",
        url="https://sso.agc.gov.sg/Act/PDPA2012",
        source_domain="sso.agc.gov.sg",
        source_name=source.name,
        source_adapter="singapore_sso",
        external_id="PDPA2012",
        retrieval_mode="live",
        discovery_method="official_search",
        validation_status="verified",
        validation_metadata={
            "final_url": "https://sso.agc.gov.sg/Act/PDPA2012",
            "fetch_method": "http_fallback",
            "document_retrieval_mode": "live",
            "http_status": 200,
            "tls_verified": True,
            "document_origin_domain": "sso.agc.gov.sg",
            "document_identity_match": True,
            "quality_status": "good",
            "quality_warnings": [],
            "content_type": "text",
            "char_count": 50000,
            "matched_indicators": ["7.1"],
        },
    )

    record = smoke.candidate_record(case, candidate, {source.name: source}, 1200)

    assert record["target_match"] is True
    assert record["official_domain_valid"] is True
    assert record["final_url_official"] is True
    assert record["page_acceptable"] is True
    assert record["acceptance_passed"] is True


def test_smoke_candidate_rejects_archived_document_and_explains_failure():
    case = next(case for case in smoke.SMOKE_CASES if case.case_id == "sgp-privacy-7.1")
    source = LegalSourceConfig(
        name="Singapore Statutes Online",
        base_url="https://sso.agc.gov.sg",
        domains=["sso.agc.gov.sg"],
    )
    candidate = LegalCandidate(
        id="pdpa-archive",
        country_code="SGP",
        title="Personal Data Protection Act 2012",
        url="https://sso.agc.gov.sg/Act/PDPA2012",
        source_name=source.name,
        source_adapter="singapore_sso",
        external_id="PDPA2012",
        retrieval_mode="fallback",
        discovery_method="known_mapping",
        validation_status="verified",
        warnings=["Document validation used fallback retrieval via wayback_machine."],
        validation_metadata={
            "final_url": "https://web.archive.org/example",
            "fetch_method": "wayback_machine",
            "document_retrieval_mode": "fallback",
            "http_status": 200,
            "tls_verified": True,
            "document_origin_domain": "web.archive.org",
            "document_identity_match": True,
            "quality_status": "good",
            "quality_warnings": [],
            "matched_indicators": ["7.1"],
        },
    )

    record = smoke.candidate_record(case, candidate, {source.name: source}, 2000)
    reasons = smoke.case_failure_reasons(case, [record])

    assert record["acceptance_passed"] is False
    assert record["fallback_explained"] is True
    assert any("not retrieved live" in reason for reason in reasons)
    assert any("redirected outside" in reason for reason in reasons)


def test_smoke_rejects_known_mapping_even_when_document_is_live_and_verified():
    case = next(case for case in smoke.SMOKE_CASES if case.case_id == "sgp-privacy-7.1")
    source = LegalSourceConfig(
        name="Singapore Statutes Online",
        base_url="https://sso.agc.gov.sg",
        domains=["sso.agc.gov.sg"],
    )
    candidate = LegalCandidate(
        id="known-pdpa",
        country_code="SGP",
        title="Personal Data Protection Act 2012",
        url="https://sso.agc.gov.sg/Act/PDPA2012",
        source_name=source.name,
        source_adapter="singapore_sso",
        retrieval_mode="live",
        discovery_method="known_mapping",
        validation_status="verified",
        validation_metadata={
            "final_url": "https://sso.agc.gov.sg/Act/PDPA2012",
            "fetch_method": "http_fallback",
            "document_retrieval_mode": "live",
            "http_status": 200,
            "tls_verified": True,
            "document_origin_domain": "sso.agc.gov.sg",
            "document_identity_match": True,
            "quality_status": "good",
            "char_count": 50000,
            "matched_indicators": ["7.1"],
        },
    )

    record = smoke.candidate_record(case, candidate, {source.name: source}, 1200)
    reasons = smoke.case_failure_reasons(case, [record])

    assert record["acceptance_passed"] is False
    assert any("official site search result" in reason for reason in reasons)


def test_smoke_redacts_sensitive_values_recursively():
    payload = {
        "api_key": "super-secret",
        "warning": "request failed: https://example.test?q=x&api_key=super-secret&token=abc",
        "nested": [{"cookie": "session=123"}],
        "authorization_warning": "Authorization: Bearer actual-secret",
        "basic_warning": "Authorization: Basic base64-secret",
        "cookie_warning": "Cookie: a=first; b=second",
        "azure_key": "Ocp-Apim-Subscription-Key: subscription-secret",
        "signed_url": (
            "https://cdn.example/law.pdf?X-Amz-Credential=credential-secret"
            "&X-Amz-Signature=signature-secret&sig=azure-signature-secret"
        ),
        "law_url": "https://flk.npc.gov.cn/detail2.html?opaque-law-id=abc",
    }

    redacted = smoke.redact_sensitive(payload)

    assert redacted["api_key"] == "[REDACTED]"
    assert "super-secret" not in redacted["warning"]
    assert "token=[REDACTED]" in redacted["warning"]
    assert redacted["nested"][0]["cookie"] == "[REDACTED]"
    assert "actual-secret" not in redacted["authorization_warning"]
    assert "base64-secret" not in redacted["basic_warning"]
    assert "first" not in redacted["cookie_warning"]
    assert "second" not in redacted["cookie_warning"]
    assert "subscription-secret" not in redacted["azure_key"]
    assert "credential-secret" not in redacted["signed_url"]
    assert "signature-secret" not in redacted["signed_url"]
    assert "azure-signature-secret" not in redacted["signed_url"]
    assert redacted["law_url"] == payload["law_url"]


def test_smoke_diagnostics_use_allowlist_and_drop_document_or_header_fields():
    diagnostics = smoke._diagnostics_record({
        "raw_hits": 2,
        "retrieval_modes": {"live": 2},
        "warnings": ["one"],
        "fetched_text": "complete legal text",
        "headers": {"Authorization": "Bearer secret"},
    })

    assert diagnostics == {
        "raw_hits": 2,
        "retrieval_modes": {"live": 2},
        "warnings": ["one"],
    }
