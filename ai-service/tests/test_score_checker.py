"""Tests for the cross-model generic-score checker (Maker/Checker)."""

from __future__ import annotations

import pytest

from agents.score_checker import ScoreCheck, check_generic_score, is_generic_scored


class _FakeProvider:
    """Minimal provider whose checker verdict is fixed per construction."""

    name = "fake-checker"

    def __init__(self, tier: int):
        self._tier = tier
        self.calls = 0

    def query(self, prompt: str, system: str = "") -> str:
        self.calls += 1
        return f'{{"matched_criterion": {self._tier}}}'


def test_bespoke_indicators_are_never_checked():
    assert not is_generic_scored("6.4")
    assert not is_generic_scored("7.1")
    assert not is_generic_scored("2.1")
    assert not is_generic_scored("5.1")
    # Everything else falls through to the generic scorer.
    assert is_generic_scored("9.3")
    assert is_generic_scored("12.7")
    assert is_generic_scored("10.1")


@pytest.mark.anyio
async def test_no_op_when_score_already_zero():
    provider = _FakeProvider(tier=1)
    result = await check_generic_score(provider, "9.3", "any quote", 0.0)
    assert result == ScoreCheck(0.0, True, "")
    assert provider.calls == 0  # a 0 score has nothing to lower — no LLM call


@pytest.mark.anyio
async def test_no_op_for_bespoke_indicator():
    provider = _FakeProvider(tier=1)
    result = await check_generic_score(provider, "7.5", "government access quote", 1.0)
    assert result.agreed and result.score == 1.0
    assert provider.calls == 0


@pytest.mark.anyio
async def test_checker_lowers_an_over_score(monkeypatch):
    # 9.3 = "1) Any restriction / 2) No restriction" -> scores 1 / 0.
    # Extractor said 1.0; the checker reads the quote as tier 2 (no restriction).
    monkeypatch.delenv("RDTII_SCORE_CHECK", raising=False)
    monkeypatch.delenv("RDTII_CHECKER_PROVIDER", raising=False)
    provider = _FakeProvider(tier=2)
    result = await check_generic_score(provider, "9.3", "The Act promotes online advertising.", 1.0)
    assert result.agreed is False
    assert result.score == 0.0
    assert "conservative minimum" in result.reason
    assert provider.calls == 1


@pytest.mark.anyio
async def test_checker_agreeing_keeps_the_score(monkeypatch):
    monkeypatch.delenv("RDTII_SCORE_CHECK", raising=False)
    provider = _FakeProvider(tier=1)  # checker agrees the restriction exists
    result = await check_generic_score(provider, "9.3", "No person shall advertise online without a licence.", 1.0)
    assert result.agreed is True
    assert result.score == 1.0


@pytest.mark.anyio
async def test_checker_never_raises_a_score(monkeypatch):
    # Even if the checker is more generous, we only ever keep the minimum.
    monkeypatch.delenv("RDTII_SCORE_CHECK", raising=False)
    provider = _FakeProvider(tier=1)  # tier 1 -> score 1.0, but extractor gave 0.5
    # 10.1 = 1) ban >1 / 2) ban one / 3) none -> 1 / 0.5 / 0
    result = await check_generic_score(provider, "10.1", "A ban applies to one product.", 0.5)
    assert result.score == 0.5  # min(0.5, 1.0) — never raised


@pytest.mark.anyio
async def test_disabled_by_env(monkeypatch):
    monkeypatch.setenv("RDTII_SCORE_CHECK", "off")
    provider = _FakeProvider(tier=2)
    result = await check_generic_score(provider, "9.3", "quote", 1.0)
    assert result == ScoreCheck(1.0, True, "")
    assert provider.calls == 0


@pytest.mark.anyio
async def test_checker_failure_is_a_no_op():
    class _Boom:
        name = "boom"

        def query(self, *a, **k):
            raise RuntimeError("provider down")

    result = await check_generic_score(_Boom(), "9.3", "quote", 1.0)
    # Infra failure must never demote a score on its own.
    assert result.agreed is True and result.score == 1.0


def test_checker_ledger_tracks_override_rate():
    """The blind-verifier ledger records agreed vs overturned checks and reports
    an override rate — our headline quality metric."""
    from agents.score_checker import _LEDGER, checker_stats, reset_checker_stats

    reset_checker_stats()
    from agents import score_checker
    # 4 checks, 1 overturned -> 25%
    score_checker._LEDGER.record("9.1", agreed=True)
    score_checker._LEDGER.record("9.1", agreed=False)
    score_checker._LEDGER.record("10.2", agreed=True)
    score_checker._LEDGER.record("12.5", agreed=True)
    s = checker_stats()
    assert s["blind_checks"] == 4
    assert s["overturned"] == 1
    assert s["override_rate"] == 0.25
    reset_checker_stats()
    assert checker_stats()["blind_checks"] == 0
