"""Tests for the /api/extract pipeline hardening (PR #8 review fixes).

Covers failure modes raised in code review:
    - Fuzzy-matched quotes whose exact offsets cannot be recovered must
      be REJECTED (not silently coerced to 0,0).
    - Provider-supplied `scope` values outside the schema literal must
      be sanitized to "unknown" (not raise Pydantic ValidationError).
    - A quote that exists in the document but NOT in the chunk the LLM
      was shown must still be rejected (kill switch is chunk-scoped, not
      document-scoped). Otherwise an LLM can cross-borrow phrases.
    - Mapping `quote_start`/`quote_end` are absolute document offsets,
      not chunk-local ones, so the audit UI highlights the right place.

A real LLM call is too expensive for unit tests, so we inject a
FakeProvider that emits canned outputs.
"""

from __future__ import annotations

import json
from typing import Any

import pytest


class FakeProvider:
    """Minimal LLMProvider stand-in returning a pre-baked dict."""

    name = "fake-provider"

    def __init__(self, response: dict[str, Any], repairs: list[dict[str, Any]] | None = None):
        self._response = response
        self._repairs = list(repairs or [])
        self.repair_calls: list[dict[str, Any]] = []

    def extract_features(
        self,
        article_text: str,
        indicator_id: str,
        feature_spec: dict,
    ) -> dict[str, Any]:
        return dict(self._response)

    def extract_batch(
        self,
        chunk_text: str,
        indicators: list[tuple[str, dict]],
    ) -> dict[str, dict[str, Any]]:
        return {ind_id: dict(self._response) for ind_id, _ in indicators}

    def repair_extraction(
        self,
        article_text: str,
        indicator_id: str,
        feature_spec: dict,
        previous_output: dict[str, Any],
        validation_errors: list[str],
    ) -> dict[str, Any]:
        self.repair_calls.append({
            "article_text": article_text,
            "indicator_id": indicator_id,
            "previous_output": dict(previous_output),
            "validation_errors": list(validation_errors),
        })
        if self._repairs:
            return dict(self._repairs.pop(0))
        return dict(previous_output)


def _patch_provider(monkeypatch, response: dict[str, Any]) -> None:
    """Force /api/extract to use FakeProvider and re-import."""
    import main as main_module

    fake = FakeProvider(response)
    # Reset the singleton and replace the factory.
    monkeypatch.setattr(main_module, "_provider", fake)
    monkeypatch.setattr(main_module, "_get_provider", lambda: fake)


def _patch_fake_provider(monkeypatch, fake: FakeProvider) -> None:
    import main as main_module

    monkeypatch.setattr(main_module, "_provider", fake)
    monkeypatch.setattr(main_module, "_get_provider", lambda: fake)


def _patch_classifier_to(monkeypatch, indicator_ids: list[str]) -> None:
    """Pin classify_indicator output so tests don't depend on keyword tuning."""
    import main as main_module

    monkeypatch.setattr(main_module, "classify_indicator", lambda _t: indicator_ids)


# ──────────────────────────────────────────────────────────────────────────
# #3 — Quote offsets unrecoverable must reject the mapping.
# ──────────────────────────────────────────────────────────────────────────


def test_fuzzy_match_with_unrecoverable_offsets_is_rejected(monkeypatch):
    from fastapi.testclient import TestClient

    import main as main_module

    # Quote shares enough characters with source for partial_ratio >= 90,
    # but no literal substring or whitespace-flexible regex match exists.
    # We craft a long source sharing many chars with quote.
    source = "Article 42. The quick brown fox jumps over the lazy dog repeatedly."
    fuzzy_quote = "The quick brown fox jumps over the lazy dog repeatedl"  # missing trailing 'y'

    response = {
        "verbatim_quote": fuzzy_quote,
        "personal_data": True,
        "has_ban": True,
        "scope": "horizontal",
    }

    _patch_provider(monkeypatch, response)
    _patch_classifier_to(monkeypatch, ["6.1"])
    # Force literal-only verification to fail so we are testing the offset gate.
    # find_quote_offsets has a regex fallback — so use a quote that even regex
    # can't recover. Easiest: cut the quote in a place that desyncs tokens.
    twisted_quote = "The quick brown FOX jumps over the lazy DOG"  # case mismatch
    response["verbatim_quote"] = twisted_quote

    client = TestClient(main_module.app)
    r = client.post("/api/extract", data={"text": source})
    assert r.status_code == 200
    data = r.json()

    # Either accepted with valid offsets, or rejected — but never accepted
    # with (0, 0) as offsets.
    for m in data["mappings"]:
        assert m["quote_end"] > m["quote_start"], (
            "mapping returned with empty highlight range; kill switch leaked"
        )
        # Offsets must point at a real substring of the source.
        assert source[m["quote_start"] : m["quote_end"]], (
            "quote offsets do not reference a real substring"
        )


# ──────────────────────────────────────────────────────────────────────────
# #4 — Invalid `scope` literal must be sanitized, not crash Pydantic.
# ──────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────
# #5 — Cross-chunk quote leak: an LLM that fabricates a quote which
# happens to exist in a *different* chunk must still be rejected.
# ──────────────────────────────────────────────────────────────────────────


def test_quote_outside_chunk_is_rejected_even_if_in_full_document(monkeypatch):
    """Verifying against `chunk.text`, not the whole document, prevents an
    LLM from "borrowing" phrases that exist elsewhere in the source.

    Test design (deliberate): the source is arranged so the *honest* match
    lives in CHUNK 2, not chunk 1. That forces the test to exercise the
    chunk-offset translation (`chunk.start + local_start`) — if a future
    refactor accidentally drops that translation, the absolute offset
    assertion below will fail, because chunk 2 starts well after byte 0.
    """
    from fastapi.testclient import TestClient

    import main as main_module

    # Order matters: article 2 contains the quote the liar will return.
    # Chunk 2 starts mid-document, so its offsets are non-zero.
    source = (
        "Article 1. Companies shall maintain a domestic data centre.\n\n"
        "Article 2. Personal data shall not be transferred abroad."
    )
    quote_from_article_2 = "Personal data shall not be transferred abroad"

    class CrossChunkLyingProvider:
        """Returns the same Article-2 quote regardless of which chunk it sees.

        On chunk 1: claims a quote that isn't in chunk 1 → MUST be rejected.
        On chunk 2: legitimately quotes from chunk 2 → should be accepted
                    AND the absolute offsets must address the original doc.
        """

        name = "fake-liar"

        def extract_features(self, article_text, indicator_id, feature_spec):
            return {
                "verbatim_quote": quote_from_article_2,
                "personal_data": True,
                "has_ban": True,
                "scope": "horizontal",
            }

        def extract_batch(
            self,
            chunk_text: str,
            indicators: list[tuple[str, dict]],
        ) -> dict[str, dict]:
            return {
                ind_id: {
                    "verbatim_quote": quote_from_article_2,
                    "personal_data": True,
                    "has_ban": True,
                    "scope": "horizontal",
                }
                for ind_id, _ in indicators
            }

    import chunker
    monkeypatch.setattr(chunker, "_MIN_CHARS", 0)

    fake = CrossChunkLyingProvider()
    main_module._provider = fake
    monkeypatch.setattr(main_module, "_get_provider", lambda: fake)
    _patch_classifier_to(monkeypatch, ["6.1"])

    client = TestClient(main_module.app)
    r = client.post("/api/extract", data={"text": source})
    assert r.status_code == 200
    data = r.json()

    # Exactly one mapping (the honest extraction from CHUNK 2).
    assert len(data["mappings"]) == 1, (
        f"expected 1 honest mapping, got {len(data['mappings'])}: {data}"
    )
    m = data["mappings"][0]
    assert m["verbatim_quote"] == quote_from_article_2

    # Absolute offsets must point at the original document. Crucially,
    # chunk 2 doesn't start at byte 0 — so an implementation that forgets
    # to translate (chunk.start + local_start) would set quote_start to a
    # local-to-chunk offset (~12), not the absolute doc offset (~70+).
    assert m["quote_start"] > 50, (
        f"quote_start={m['quote_start']} looks chunk-local; "
        "the offset translation has regressed"
    )
    assert source[m["quote_start"] : m["quote_end"]] == quote_from_article_2, (
        f"offsets {m['quote_start']}..{m['quote_end']} don't address the original text"
    )

    # The cross-chunk lie (chunk 1's call) must surface in `rejected[]`.
    cross_chunk_rejections = [
        rej
        for rej in data["rejected"]
        if "data centre" in rej.get("chunk_preview", "")
    ]
    assert cross_chunk_rejections, (
        "cross-chunk borrowed quote slipped through: "
        f"{data['rejected']}"
    )
    assert "not found in chunk" in cross_chunk_rejections[0]["reason"]


def test_runtime_repair_loop_fixes_bad_quote(monkeypatch):
    """A quote verification failure should be fed back to the provider once,
    allowing it to return an exact source substring before the mapping is
    scored and emitted."""
    from fastapi.testclient import TestClient

    import main as main_module

    monkeypatch.setenv("RDTII_REPAIR_MAX_ATTEMPTS", "1")
    source = "Article 1. Personal data shall not be transferred abroad."
    exact_quote = "Personal data shall not be transferred abroad"

    fake = FakeProvider(
        {
            "verbatim_quote": "Personal data cannot be transferred overseas",
            "personal_data": True,
            "has_ban": True,
            "scope": "horizontal",
        },
        repairs=[
            {
                "verbatim_quote": exact_quote,
                "personal_data": True,
                "has_ban": True,
                "scope": "horizontal",
            }
        ],
    )
    _patch_fake_provider(monkeypatch, fake)
    _patch_classifier_to(monkeypatch, ["6.1"])

    client = TestClient(main_module.app)
    r = client.post("/api/extract", data={"text": source})
    assert r.status_code == 200
    data = r.json()

    assert len(fake.repair_calls) == 1
    assert "not found in chunk" in "; ".join(fake.repair_calls[0]["validation_errors"])
    assert len(data["mappings"]) == 1
    assert data["mappings"][0]["verbatim_quote"] == exact_quote
    assert data["rejected"] == []


def test_runtime_repair_loop_preserves_metadata_when_repair_omits_it(monkeypatch):
    from fastapi.testclient import TestClient

    import main as main_module

    monkeypatch.setenv("RDTII_REPAIR_MAX_ATTEMPTS", "1")
    source = "Article 1. Personal data shall not be transferred abroad."
    exact_quote = "Personal data shall not be transferred abroad"

    fake = FakeProvider(
        {
            "verbatim_quote": "Personal data cannot be transferred overseas",
            "personal_data": True,
            "has_ban": True,
            "scope": "horizontal",
            "source_legislation": "Singapore Personal Data Protection Act (PDPA), 2012",
            "last_update": "2012",
        },
        repairs=[
            {
                "verbatim_quote": exact_quote,
                "personal_data": True,
                "has_ban": True,
            }
        ],
    )
    _patch_fake_provider(monkeypatch, fake)
    _patch_classifier_to(monkeypatch, ["6.1"])

    client = TestClient(main_module.app)
    r = client.post("/api/extract", data={"text": source})
    assert r.status_code == 200
    data = r.json()

    assert len(data["mappings"]) == 1
    m = data["mappings"][0]
    assert m["source_legislation"].startswith("Singapore Personal Data Protection Act")
    assert m["scope"] == "horizontal"


def test_runtime_repair_loop_handles_non_string_quote_without_500(monkeypatch):
    from fastapi.testclient import TestClient

    import main as main_module

    monkeypatch.setenv("RDTII_REPAIR_MAX_ATTEMPTS", "1")
    source = "Article 1. Personal data shall not be transferred abroad."
    exact_quote = "Personal data shall not be transferred abroad"

    fake = FakeProvider(
        {
            "verbatim_quote": ["Personal data"],
            "personal_data": True,
            "has_ban": True,
            "scope": "horizontal",
        },
        repairs=[
            {
                "verbatim_quote": exact_quote,
                "personal_data": True,
                "has_ban": True,
                "scope": "horizontal",
            }
        ],
    )
    _patch_fake_provider(monkeypatch, fake)
    _patch_classifier_to(monkeypatch, ["6.1"])

    client = TestClient(main_module.app)
    r = client.post("/api/extract", data={"text": source})
    assert r.status_code == 200
    data = r.json()

    assert len(fake.repair_calls) == 1
    assert "verbatim_quote must be a string" in "; ".join(fake.repair_calls[0]["validation_errors"])
    assert len(data["mappings"]) == 1
    assert data["mappings"][0]["verbatim_quote"] == exact_quote


def test_runtime_float_string_feature_does_not_500(monkeypatch):
    from fastapi.testclient import TestClient

    import main as main_module

    monkeypatch.setenv("RDTII_REPAIR_MAX_ATTEMPTS", "0")
    source = "Article 1. The tariff rate shall be 50 percent for covered digital products."
    quote = "The tariff rate shall be 50 percent for covered digital products"

    fake = FakeProvider({
        "verbatim_quote": quote,
        "tariff_rate": "50",
        "scope": "sectoral",
    })
    _patch_fake_provider(monkeypatch, fake)
    _patch_classifier_to(monkeypatch, ["1.1"])

    client = TestClient(main_module.app)
    r = client.post("/api/extract", data={"text": source})
    assert r.status_code == 200
    data = r.json()

    assert len(data["mappings"]) == 1
    assert data["mappings"][0]["score"] == 0.5
    assert data["mappings"][0]["features"]["tariff_rate"] == 50.0


def test_runtime_validation_flag_does_not_trigger_repair(monkeypatch):
    from fastapi.testclient import TestClient

    import main as main_module

    monkeypatch.setenv("RDTII_REPAIR_MAX_ATTEMPTS", "1")
    source = "Article 1. The objective of this Act is to provide a legal framework for personal data protection."
    quote = "The objective of this Act is to provide a legal framework for personal data protection"

    fake = FakeProvider({
        "verbatim_quote": quote,
        "has_comprehensive_framework": True,
        "scope": "horizontal",
    })
    _patch_fake_provider(monkeypatch, fake)
    _patch_classifier_to(monkeypatch, ["7.1"])

    client = TestClient(main_module.app)
    r = client.post("/api/extract", data={"text": source})
    assert r.status_code == 200
    data = r.json()

    assert len(fake.repair_calls) == 0
    assert len(data["mappings"]) == 1
    assert data["mappings"][0]["requires_human_review"] is True
    assert data["mappings"][0]["flag_reasons"]


def test_runtime_repair_loop_fixes_validation_reject(monkeypatch):
    """A deterministic validation reject, such as a section heading quote,
    should be repairable before the candidate is finally rejected."""
    from fastapi.testclient import TestClient

    import main as main_module

    monkeypatch.setenv("RDTII_REPAIR_MAX_ATTEMPTS", "1")
    source = "PART II - DATA PROTECTION. Personal data shall not be transferred abroad."
    exact_quote = "Personal data shall not be transferred abroad"

    fake = FakeProvider(
        {
            "verbatim_quote": "PART II - DATA PROTECTION",
            "personal_data": True,
            "has_ban": True,
            "scope": "horizontal",
        },
        repairs=[
            {
                "verbatim_quote": exact_quote,
                "personal_data": True,
                "has_ban": True,
                "scope": "horizontal",
            }
        ],
    )
    _patch_fake_provider(monkeypatch, fake)
    _patch_classifier_to(monkeypatch, ["6.1"])

    client = TestClient(main_module.app)
    r = client.post("/api/extract", data={"text": source})
    assert r.status_code == 200
    data = r.json()

    assert len(fake.repair_calls) == 1
    assert any("section/part heading" in err for err in fake.repair_calls[0]["validation_errors"])
    assert len(data["mappings"]) == 1
    assert data["mappings"][0]["verbatim_quote"] == exact_quote
    assert data["rejected"] == []


def test_runtime_repair_loop_rejects_when_repair_still_invalid(monkeypatch):
    from fastapi.testclient import TestClient

    import main as main_module

    monkeypatch.setenv("RDTII_REPAIR_MAX_ATTEMPTS", "1")
    source = "Article 1. Personal data shall not be transferred abroad."

    fake = FakeProvider(
        {
            "verbatim_quote": "not in the source",
            "personal_data": True,
            "has_ban": True,
            "scope": "horizontal",
        },
        repairs=[
            {
                "verbatim_quote": "still not in the source",
                "personal_data": True,
                "has_ban": True,
                "scope": "horizontal",
            }
        ],
    )
    _patch_fake_provider(monkeypatch, fake)
    _patch_classifier_to(monkeypatch, ["6.1"])

    client = TestClient(main_module.app)
    r = client.post("/api/extract", data={"text": source})
    assert r.status_code == 200
    data = r.json()

    assert len(fake.repair_calls) == 1
    assert data["mappings"] == []
    assert data["rejected"]
    assert "not found in chunk" in data["rejected"][0]["reason"]


def test_runtime_feature_normalization_prevents_string_false_scoring_bug(monkeypatch):
    """String booleans from LLM JSON must be coerced before scoring.

    Without this, Python's bool("false") would incorrectly count a false
    feature as true and inflate the score.
    """
    from fastapi.testclient import TestClient

    import main as main_module

    monkeypatch.setenv("RDTII_REPAIR_MAX_ATTEMPTS", "0")
    # Precision-first mode: this test asserts the eligibility gate's hard-drop
    # path (the default flag mode keeps + flags instead of rejecting).
    monkeypatch.setenv("RDTII_ELIGIBILITY_MODE", "reject")
    source = "Article 1. Personal data shall be freely transferred abroad."
    quote = "Personal data shall be freely transferred abroad"

    fake = FakeProvider({
        "verbatim_quote": quote,
        "personal_data": "true",
        "has_ban": "false",
        "has_local_processing": "false",
        "scope": "horizontal",
    })
    _patch_fake_provider(monkeypatch, fake)
    _patch_classifier_to(monkeypatch, ["6.1"])

    client = TestClient(main_module.app)
    r = client.post("/api/extract", data={"text": source})
    assert r.status_code == 200
    data = r.json()

    assert len(fake.repair_calls) == 0
    # A topical transfer sentence with neither a ban nor local-processing
    # requirement is now rejected before scoring; normalized booleans remain
    # visible in the structured audit payload.
    assert data["mappings"] == []
    assert data["rejected"]
    raw = data["rejected"][0]["raw_output"]
    assert raw["personal_data"] is True
    assert raw["has_ban"] is False
    assert raw["has_local_processing"] is False


def test_streaming_runtime_uses_same_feature_normalization(monkeypatch):
    from fastapi.testclient import TestClient

    import main as main_module

    monkeypatch.setenv("RDTII_REPAIR_MAX_ATTEMPTS", "0")
    source = "Article 1. Personal data shall be freely transferred abroad."
    quote = "Personal data shall be freely transferred abroad"

    fake = FakeProvider({
        "verbatim_quote": quote,
        "personal_data": "true",
        "has_ban": "false",
        "has_local_processing": "false",
        "scope": "horizontal",
    })
    _patch_fake_provider(monkeypatch, fake)
    _patch_classifier_to(monkeypatch, ["6.1"])

    client = TestClient(main_module.app)
    r = client.post("/api/extract/stream", data={"text": source})
    assert r.status_code == 200

    mapping_payloads = []
    rejection_payloads = []
    for line in r.text.splitlines():
        if line.startswith("data: ") and '"score"' in line:
            mapping_payloads.append(json.loads(line.removeprefix("data: ")))
        elif line.startswith("data: ") and '"candidate_indicator": "6.1"' in line:
            rejection_payloads.append(json.loads(line.removeprefix("data: ")))

    assert mapping_payloads == []
    assert len(rejection_payloads) == 1
    assert rejection_payloads[0]["raw_output"]["has_ban"] is False


def test_streaming_runtime_repair_loop_fixes_bad_quote(monkeypatch):
    from fastapi.testclient import TestClient

    import main as main_module

    monkeypatch.setenv("RDTII_REPAIR_MAX_ATTEMPTS", "1")
    source = "Article 1. Personal data shall not be transferred abroad."
    exact_quote = "Personal data shall not be transferred abroad"

    fake = FakeProvider(
        {
            "verbatim_quote": "Personal data cannot be transferred overseas",
            "personal_data": True,
            "has_ban": True,
            "scope": "horizontal",
        },
        repairs=[
            {
                "verbatim_quote": exact_quote,
                "personal_data": True,
                "has_ban": True,
                "scope": "horizontal",
            }
        ],
    )
    _patch_fake_provider(monkeypatch, fake)
    _patch_classifier_to(monkeypatch, ["6.1"])

    client = TestClient(main_module.app)
    r = client.post("/api/extract/stream", data={"text": source})
    assert r.status_code == 200

    mapping_payloads = []
    rejected_payloads = []
    current_event = None
    for line in r.text.splitlines():
        if line.startswith("event: "):
            current_event = line.removeprefix("event: ")
        elif line.startswith("data: "):
            payload = json.loads(line.removeprefix("data: "))
            if current_event == "mapping":
                mapping_payloads.append(payload)
            elif current_event == "rejected":
                rejected_payloads.append(payload)

    assert len(fake.repair_calls) == 1
    assert "not found in chunk" in "; ".join(fake.repair_calls[0]["validation_errors"])
    assert rejected_payloads == []
    assert len(mapping_payloads) == 1
    assert mapping_payloads[0]["verbatim_quote"] == exact_quote


@pytest.mark.parametrize(
    "bad_scope",
    ["global", "regional", "national", "", None, "Sectoral ", "HORIZONTAL"],
)
def test_invalid_scope_is_sanitized(monkeypatch, bad_scope):
    from fastapi.testclient import TestClient

    import main as main_module

    source = "Article 1. Personal data shall not be transferred abroad."
    quote = "Personal data shall not be transferred abroad."

    response = {
        "verbatim_quote": quote,
        "personal_data": True,
        "horizontal_scope": True,
        "has_ban": True,
        "scope": bad_scope,
    }

    _patch_provider(monkeypatch, response)
    _patch_classifier_to(monkeypatch, ["6.1"])
    monkeypatch.setattr(main_module, "classify_coverage", lambda **kwargs: {"scope": "unknown", "reasons": []})

    client = TestClient(main_module.app)
    r = client.post("/api/extract", data={"text": source})
    assert r.status_code == 200, f"crashed on scope={bad_scope!r}: {r.text}"
    data = r.json()
    assert data["mappings"], "expected a mapping even with invalid scope"
    scope = data["mappings"][0]["scope"]
    assert scope in {"horizontal", "sectoral", "unknown"}, (
        f"scope leaked invalid value: {scope!r}"
    )
    # Specifically: trailing-space + uppercase should normalise to lowercase.
    if isinstance(bad_scope, str) and bad_scope.strip().lower() in {
        "horizontal",
        "sectoral",
    }:
        assert scope == bad_scope.strip().lower()
    else:
        assert scope == "unknown"


# ──────────────────────────────────────────────────────────────────────────
# /health and /providers must surface a misconfigured RDTII_LLM_PROVIDER
# instead of pretending the invalid name is a valid choice.
# ──────────────────────────────────────────────────────────────────────────


def test_health_reports_misconfigured_when_provider_unknown(monkeypatch):
    """If RDTII_LLM_PROVIDER doesn't resolve, /health must say so —
    `active_provider` must be null (not echo the bad value) and `status`
    must flip to "misconfigured". Otherwise consumers can't tell a typo
    from a healthy config."""
    from fastapi.testclient import TestClient

    import main as main_module

    monkeypatch.setenv("RDTII_LLM_PROVIDER", "totally-not-a-provider")
    client = TestClient(main_module.app)

    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "misconfigured"
    assert body["active_provider"] is None
    assert body["provider_env"] == "totally-not-a-provider"
    assert "totally-not-a-provider" not in body["available_providers"]


def test_providers_reports_invalid_with_alias(monkeypatch):
    """Same contract on /providers. `active` must be null; `active_alias`
    must carry the raw bad value for debugging."""
    from fastapi.testclient import TestClient

    import main as main_module

    monkeypatch.setenv("RDTII_LLM_PROVIDER", "gpt-9000")
    client = TestClient(main_module.app)

    r = client.get("/providers")
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is None
    assert body["active_alias"] == "gpt-9000"
    assert body["name_recognised"] is False


def test_providers_active_is_in_available_when_recognised(monkeypatch):
    """The headline contract: when the name is recognised, `active` must
    appear in `available`, even when the user supplied an alias.

    Note: `name_recognised: True` does NOT promise instantiation will
    succeed — that's only proven by an actual /api/extract call.
    """
    from fastapi.testclient import TestClient

    import main as main_module

    monkeypatch.setenv("RDTII_LLM_PROVIDER", "llama3")  # alias
    client = TestClient(main_module.app)

    r = client.get("/providers")
    assert r.status_code == 200
    body = r.json()
    assert body["name_recognised"] is True
    assert body["active"] == "llama-3-local"  # resolved canonical
    assert body["active"] in body["available"]
    assert body["active_alias"] == "llama3"


# ──────────────────────────────────────────────────────────────────────────
# Formatting Interceptor Tests (UN Compliance)
# ──────────────────────────────────────────────────────────────────────────


def test_formatting_interceptor_un_compliance(monkeypatch):
    """Verify that formatting interceptor correctly cleans up and formats the fields

    to UN ESCAP RDTII 2.1 specifications:
      1. Strips clause/article numbers from 'Act and/or practice' (source_legislation)
         and formats it as [Country] [Law Name] ([Abbreviation]), [Year], [Law Number].
      2. Prepends [Article X] or [Section Y] to the front of 'Impacts or comments' (impact).
      3. Normalizes last_update and timeframe_column to use Month Name YYYY format.
    """
    from fastapi.testclient import TestClient
    import main as main_module

    source = "Article 18. Personal data shall not be transferred abroad."
    quote = "Personal data shall not be transferred abroad"

    # LLM raw output with article in title, non-normalized date, etc.
    response = {
        "verbatim_quote": quote,
        "article_clause": "Article 18",
        "personal_data": True,
        "has_ban": True,
        "scope": "horizontal",
        "source_legislation": "Personal Data Protection Act (PDPA) 2012 Article 18",
        "last_update": "05/2012",  # non-normalized
        "source_url": "https://www.sso.gov.sg/PDPA",
    }

    _patch_provider(monkeypatch, response)
    _patch_classifier_to(monkeypatch, ["6.1"])

    # Mock crawler's network requests to keep test purely local and fast
    async def fake_fetch(url):
        return {"type": "text", "text": source}
    async def fake_verify_timeline(url, claimed_date):
        return {"verified": True, "best_date": "05/2012", "verification_log": "Mocked", "source_details": []}
    monkeypatch.setattr("crawler.fetch_legal_content", fake_fetch)
    monkeypatch.setattr("crawler.verify_law_timeline", fake_verify_timeline)

    client = TestClient(main_module.app)
    r = client.post("/api/extract", data={"text": source, "source_url": "https://www.sso.gov.sg/PDPA"})
    assert r.status_code == 200
    data = r.json()
    
    assert len(data["mappings"]) == 1
    m = data["mappings"][0]

    # Rule 1: Clean and format source_legislation (Prepend country, strip article)
    assert m["source_legislation"] == "Singapore Personal Data Protection Act (PDPA), 2012"
    assert m["article_clause"] == "Article 18"

    # Rule 2: Prepend article/clause to the impact column
    assert m["impact"].startswith("[Article 18]")

    # Rule 3: Timeframe dates calibrated to Month Name YYYY format
    assert m["last_update"] == "May 2012"
    assert "May 2012" in m["features"]["_timeframe_column"]


def test_extract_rejects_crawled_website_error_page(monkeypatch):
    from fastapi.testclient import TestClient
    import main as main_module

    async def fake_fetch(url):
        return {
            "type": "text",
            "text": "Page Not Found. We are sorry, the page you are looking for may have been removed, had its name changed, or is temporarily unavailable.",
        }

    monkeypatch.setattr("crawler.fetch_legal_content", fake_fetch)

    client = TestClient(main_module.app)
    response = client.post("/api/extract", data={"source_url": "https://www.imda.gov.sg/page-not-found"})

    assert response.status_code == 400
    assert "website error page" in response.json()["detail"]


def test_stream_extract_rejects_crawled_website_error_page(monkeypatch):
    from fastapi.testclient import TestClient
    import main as main_module

    async def fake_fetch(url):
        return {
            "type": "text",
            "text": "Page Not Found. We are sorry, the page you are looking for may have been removed, had its name changed, or is temporarily unavailable.",
        }

    monkeypatch.setattr("crawler.fetch_legal_content", fake_fetch)

    client = TestClient(main_module.app)
    response = client.post("/api/extract/stream", data={"source_url": "https://www.imda.gov.sg/page-not-found"})

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "website error page" in response.text


def test_null_optional_text_fields_do_not_crash_extraction(monkeypatch):
    from fastapi.testclient import TestClient
    import main as main_module

    source = "Article 1. Personal data shall not be transferred abroad."
    quote = "Personal data shall not be transferred abroad"
    response = {
        "verbatim_quote": quote,
        "personal_data": True,
        "has_ban": True,
        "scope": "horizontal",
        "source_legislation": None,
        "last_update": None,
        "source_url": None,
        "coverage": None,
        "cluster": None,
        "name": None,
        "policy_description": None,
    }

    _patch_provider(monkeypatch, response)
    _patch_classifier_to(monkeypatch, ["6.1"])

    client = TestClient(main_module.app)
    result = client.post("/api/extract", data={"text": source})

    assert result.status_code == 200
    mapping = result.json()["mappings"][0]
    assert isinstance(mapping["coverage"], str)
    assert mapping["cluster"] == ""
    assert mapping["name"] == ""
    assert mapping["policy_description"] == ""


def test_stream_pdf_parse_error_returns_sse_error(monkeypatch):
    from fastapi.testclient import TestClient
    import main as main_module

    async def fake_fetch(url):
        return {"type": "pdf", "pdf_path": "/tmp/missing.pdf"}

    def fake_read_pdf(path):
        raise RuntimeError("cannot parse pdf")

    monkeypatch.setattr("crawler.fetch_legal_content", fake_fetch)
    monkeypatch.setattr("pdf_reader.read_pdf", fake_read_pdf)

    client = TestClient(main_module.app)
    response = client.post("/api/extract/stream", data={"source_url": "https://example.test/law.pdf"})

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "PDF parsing failed: cannot parse pdf" in response.text


def test_recent_corrections_degrades_without_psycopg2(monkeypatch):
    # The judge CLI's lean install has no psycopg2; the negative-few-shot
    # helper must return "" instead of crashing every extraction batch.
    import builtins
    from providers.base import LLMProvider

    real_import = builtins.__import__

    def no_psycopg2(name, *a, **k):
        if name == "psycopg2":
            raise ModuleNotFoundError("No module named 'psycopg2'")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_psycopg2)
    assert LLMProvider._get_recent_corrections() == ""


def test_runtime_repair_loop_expands_fragment_quote(monkeypatch):
    """A verbatim mid-sentence fragment ("kept in Malaysia") is caught at
    prepare time and repaired to the full provision limb, instead of sailing
    through mapping only to be dropped at submission validation (the MYS 6.2
    seed regression)."""
    from fastapi.testclient import TestClient

    import main as main_module

    monkeypatch.setenv("RDTII_REPAIR_MAX_ATTEMPTS", "1")
    source = (
        "24. (1) Every taxable person shall keep complete and true records. "
        "(2) The records shall be kept in Malaysia, except as otherwise "
        "approved by the Director General."
    )
    full_quote = (
        "kept in Malaysia, except as otherwise approved by the Director General"
    )

    fake = FakeProvider(
        {
            "verbatim_quote": "kept in Malaysia",
            "personal_data": False,
            "has_local_storage": True,
            "scope": "sectoral",
        },
        repairs=[
            {
                "verbatim_quote": full_quote,
                "personal_data": False,
                "has_local_storage": True,
                "scope": "sectoral",
            }
        ],
    )
    _patch_fake_provider(monkeypatch, fake)
    _patch_classifier_to(monkeypatch, ["6.2"])

    client = TestClient(main_module.app)
    r = client.post("/api/extract", data={"text": source})
    assert r.status_code == 200
    data = r.json()

    assert len(fake.repair_calls) == 1
    assert any("short fragment" in err for err in fake.repair_calls[0]["validation_errors"])
    assert len(data["mappings"]) == 1
    assert data["mappings"][0]["verbatim_quote"] == full_quote


def test_runtime_repair_loop_replaces_citation_style_quote(monkeypatch):
    """A statute-name + section-reference quote with no operative language
    (e.g. a seed excerpt's descriptive header line) is caught at prepare time
    and repaired to operative provision text (the AUS 7.2 seed regression)."""
    from fastapi.testclient import TestClient

    import main as main_module

    monkeypatch.setenv("RDTII_REPAIR_MAX_ATTEMPTS", "1")
    header = (
        "Cyber Security Act 2024 (No. 98, 2024): Section 3 Objects and "
        "Section 27 Ransomware payment reporting"
    )
    operative = (
        "The reporting business entity must give the designated Commonwealth "
        "body a report within 72 hours of making the ransomware payment"
    )
    source = header + "\n\n27. " + operative + "."

    fake = FakeProvider(
        {
            "verbatim_quote": header,
            "has_dedicated_cyber_framework": True,
            "scope": "horizontal",
        },
        repairs=[
            {
                "verbatim_quote": operative,
                "has_dedicated_cyber_framework": True,
                "scope": "horizontal",
            }
        ],
    )
    _patch_fake_provider(monkeypatch, fake)
    _patch_classifier_to(monkeypatch, ["7.2"])

    client = TestClient(main_module.app)
    r = client.post("/api/extract", data={"text": source})
    assert r.status_code == 200
    data = r.json()

    assert len(fake.repair_calls) == 1
    assert any("citation/title" in err for err in fake.repair_calls[0]["validation_errors"])
    assert len(data["mappings"]) == 1
    assert data["mappings"][0]["verbatim_quote"] == operative


def test_leading_section_citation_quote_is_citation_style():
    """'Section 19(2) — Special restrictions …:' — a quote opening with a
    section citation + separator is a constructed heading, caught at prepare
    time (found by the run6 independent verbatim audit; the NSW PPIP row)."""
    from extraction_repair import _is_citation_style_quote

    assert _is_citation_style_quote(
        "Section 19(2) — Special restrictions on disclosure of "
        "personal information (cross-border):"
    )
    # A real provision that merely cites a section mid-text is spared.
    assert not _is_citation_style_quote(
        "Section 19(2) provides that an agency must not disclose personal "
        "information to any person or body outside New South Wales"
    )
