"""Smoke tests for concrete provider repair paths.

These tests mock each SDK/network boundary and exercise the provider method
itself, catching attribute or response-shape mistakes before runtime repair
hits a real vendor.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any


REPAIRED = {
    "verbatim_quote": "Personal data shall not be transferred abroad",
    "personal_data": True,
    "has_ban": True,
    "scope": "horizontal",
}

ARTICLE_TEXT = "Article 1. Personal data shall not be transferred abroad."
FEATURE_SPEC = {
    "personal_data": {"type": "bool", "description": "Covers personal data"},
    "has_ban": {"type": "bool", "description": "Contains a transfer ban"},
}


class FakeChatCompletions:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(self.payload))
                )
            ],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
        )


class FakeOpenAIClient:
    def __init__(self, payload: dict[str, Any]):
        self.chat = SimpleNamespace(completions=FakeChatCompletions(payload))


def _repair(provider) -> dict[str, Any]:
    return provider.repair_extraction(
        article_text=ARTICLE_TEXT,
        indicator_id="6.1",
        feature_spec=FEATURE_SPEC,
        previous_output={"verbatim_quote": "Personal data cannot go overseas"},
        validation_errors=["verbatim_quote not found in chunk"],
    )


def test_openai_compatible_repair_extraction_uses_json_mode():
    from providers.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider.model_name = "fake-openai-compatible"
    provider._client = FakeOpenAIClient(REPAIRED)
    provider._input_price = 0.0
    provider._output_price = 0.0

    assert _repair(provider) == REPAIRED

    call = provider._client.chat.completions.calls[0]
    assert call["temperature"] == 0
    assert call["response_format"] == {"type": "json_object"}
    assert provider.last_usage.raw_response == json.dumps(REPAIRED)


def test_claude_repair_extraction_parses_text_blocks():
    from providers.claude import ClaudeProvider

    class FakeMessages:
        def __init__(self):
            self.calls: list[dict[str, Any]] = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(type="text", text=json.dumps(REPAIRED)),
                ],
                usage=SimpleNamespace(input_tokens=13, output_tokens=8),
            )

    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider.model_name = "fake-claude"
    provider._client = SimpleNamespace(messages=FakeMessages())

    assert _repair(provider) == REPAIRED

    call = provider._client.messages.calls[0]
    assert call["temperature"] == 0
    assert call["system"] == "Output ONLY valid JSON. No prose, no markdown fences."
    assert provider.last_usage.raw_response == json.dumps(REPAIRED)


def test_gemini_repair_extraction_parses_json_response():
    from providers.gemini import GeminiProvider

    class FakeGeminiModel:
        def __init__(self):
            self.calls: list[dict[str, Any]] = []

        def generate_content(self, prompt, generation_config):
            self.calls.append({
                "prompt": prompt,
                "generation_config": generation_config,
            })
            return SimpleNamespace(
                text=json.dumps(REPAIRED),
                usage_metadata=SimpleNamespace(
                    prompt_token_count=17,
                    candidates_token_count=9,
                ),
            )

    provider = GeminiProvider.__new__(GeminiProvider)
    provider.model_name = "fake-gemini"
    provider._model = FakeGeminiModel()

    assert _repair(provider) == REPAIRED
    assert len(provider._model.calls) == 1
    assert provider.last_usage.raw_response == json.dumps(REPAIRED)


def test_ollama_repair_extraction_uses_local_openai_client(monkeypatch):
    import openai

    from providers.ollama import OllamaProvider

    fake_client = FakeOpenAIClient(REPAIRED)
    seen_kwargs: list[dict[str, Any]] = []

    def fake_openai(**kwargs):
        seen_kwargs.append(kwargs)
        return fake_client

    monkeypatch.setattr(openai, "OpenAI", fake_openai)

    provider = OllamaProvider.__new__(OllamaProvider)
    provider.raw_api_key = "ollama-local"
    provider.base_url = "http://ollama.test/v1"
    provider.model_name = "fake-ollama"

    assert _repair(provider) == REPAIRED

    assert seen_kwargs == [
        {"api_key": "ollama-local", "base_url": "http://ollama.test/v1"}
    ]
    call = fake_client.chat.completions.calls[0]
    assert call["temperature"] == 0
    assert provider.last_usage.raw_response == json.dumps(REPAIRED)
