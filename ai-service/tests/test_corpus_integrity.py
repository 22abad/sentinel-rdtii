"""Corpus-integrity verdict tests (tools/restore_corpus.judge_integrity).

Guards the manifest-vs-disk corruption detector that caught the 34-file IDN
corpus poisoning (fill_corpus overwrote good full texts with short wrong
search hits). The detector must flag a truncated file, pass an exact match,
and never flag a legitimately drifted-but-comparable re-fetch.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.restore_corpus import judge_integrity  # noqa: E402


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def test_exact_sha_match_is_clean():
    text = "the full law text " * 1000
    corrupt, _ = judge_integrity(text, _sha(text), len(text))
    assert corrupt is False


def test_truncated_file_is_flagged():
    # disk is a 3% stub of the recorded 100k good text -> corrupt (the IDN mode)
    corrupt, reason = judge_integrity("x" * 3000, "deadbeef", 100_000)
    assert corrupt is True
    assert "truncated" in reason


def test_missing_file_is_flagged():
    corrupt, reason = judge_integrity(None, "deadbeef", 100_000)
    assert corrupt is True
    assert "missing" in reason


def test_comparable_size_change_is_not_flagged():
    # sha differs but length is within range of the baseline -> re-fetch drift,
    # not the truncation failure mode. Must NOT be flagged (would false-positive
    # every legitimately re-rendered bpk page).
    corrupt, _ = judge_integrity("y" * 98_000, "deadbeef", 100_000)
    assert corrupt is False


def test_no_baseline_cannot_judge():
    corrupt, _ = judge_integrity("anything", "", 0)
    assert corrupt is False


def test_boundary_just_under_half_is_flagged():
    corrupt, _ = judge_integrity("z" * 49_999, "deadbeef", 100_000)
    assert corrupt is True


def test_boundary_just_over_half_is_clean():
    corrupt, _ = judge_integrity("z" * 50_001, "deadbeef", 100_000)
    assert corrupt is False


def _quality(text):
    import sys
    from pathlib import Path
    _repo = Path(__file__).resolve().parents[2]
    if str(_repo) not in sys.path:
        sys.path.insert(0, str(_repo))
    from tools.restore_corpus import classify_text_quality
    return classify_text_quality(text)[0]


def test_quality_classifier_distinguishes_statute_from_summary_and_stub():
    statute = "\n".join(
        f"Article {i}. The controller shall implement measures for the protection of "
        f"personal data, retention limits, and accountability under this section. " * 3
        for i in range(1, 12)
    )
    assert len(statute) > 3000  # a full statute, not a stub
    assert _quality(statute) == "STATUTE"
    # a law-firm summary of a law carries no verbatim provisions
    summary = ("On 17 December 2021, the Parliament passed the Personal Data Protection "
               "Law which will establish broader obligations. This client alert gives an "
               "overview of the key changes expected to take effect next year. " * 20)
    assert _quality(summary) == "SUMMARY"
    # a short fetch stub is not a full statute
    assert _quality("Personal Information Protection Law. Effective 2021.") == "STUB"
    # a non-English statute (Indonesian 'Pasal') must classify as STATUTE, not
    # summary — the classifier speaks the corpus's languages.
    idn = "\n".join(
        f"Pasal {i}. Penyelenggara sistem elektronik wajib melindungi data pribadi "
        f"sesuai ketentuan peraturan ini dan menjamin keamanan pemrosesan data. " * 3
        for i in range(1, 21)
    )
    assert len(idn) > 3000
    assert _quality(idn) == "STATUTE"
