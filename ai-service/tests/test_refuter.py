"""TDD (red-first) for the adversarial-refuter decision seam.

N independent models each try to REFUTE a NEW-law mapping; the mapping is
killed only when a MAJORITY refute it (default). The
verdict is the pure, testable seam — the LLM calls are a separate adapter.
"""
from __future__ import annotations

import sys
from pathlib import Path

_AI = Path(__file__).resolve().parents[1]
if str(_AI) not in sys.path:
    sys.path.insert(0, str(_AI))


def test_majority_refute_kills_the_mapping():
    from agents.refuter import refuter_verdict

    v = refuter_verdict([True, True, False])   # 2 of 3 refute
    assert v["refuted"] is True
    assert v["refute_rate"] == round(2 / 3, 3)
    assert v["votes"] == 3


def test_minority_refute_survives():
    from agents.refuter import refuter_verdict

    v = refuter_verdict([True, False, False])  # 1 of 3
    assert v["refuted"] is False
    assert v["refute_rate"] == round(1 / 3, 3)


def test_no_votes_is_not_refuted():
    from agents.refuter import refuter_verdict

    v = refuter_verdict([])
    assert v["refuted"] is False
    assert v["refute_rate"] == 0.0


def test_threshold_is_configurable_conservative():
    from agents.refuter import refuter_verdict

    # a strict gate: kill if ANY refuter refutes (threshold just above 0)
    v = refuter_verdict([True, False, False], kill_threshold=0.01)
    assert v["refuted"] is True


class _FakeProvider:
    """Returns canned refute responses in order; records prompts seen."""
    name = "fake"

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def query(self, prompt, system=""):
        r = self._responses[self.calls % len(self._responses)]
        self.calls += 1
        return r


def test_refute_mapping_runs_n_votes_and_aggregates(monkeypatch):
    import asyncio
    from agents.refuter import refute_mapping

    # 2 of 3 say refuted -> majority -> refuted True
    prov = _FakeProvider(['{"refuted": true}', '{"refuted": false}', '{"refuted": true}'])
    v = asyncio.run(refute_mapping(prov, quote="X may transfer data", indicator="6.4",
                                   criterion="conditional cross-border transfer", n_votes=3))
    assert prov.calls == 3
    assert v["votes"] == 3 and v["refuted"] is True


def test_refute_mapping_unparseable_vote_counts_as_not_refuted(monkeypatch):
    import asyncio
    from agents.refuter import refute_mapping

    # garbage + one refute -> 1/2 rate 0.5, not > 0.5 -> survives
    prov = _FakeProvider(['not json', '{"refuted": true}'])
    v = asyncio.run(refute_mapping(prov, quote="q", indicator="7.1", criterion="c", n_votes=2))
    assert v["refuted"] is False
