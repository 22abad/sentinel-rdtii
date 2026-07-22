"""Hindi (Devanagari) must survive the same extraction gates as English.

Regression: Hindi PDFs (India DPDP Act 2023) extracted fine but produced only
English mappings — Hindi-only chunks matched no classifier phrase, so they were
silently dropped at the `if indicators:` router in streaming_extraction before
the LLM ever saw them (no `rejected` event — just ignored). The classifier
already carried zh/th/vi/ms phrase lists; Hindi was simply never added. These
tests pin the Devanagari coverage across the Round-1 indicators (P6 6.1-6.4,
P7 7.1-7.5) at both gates: classifier routing and the validation quote gates.
"""

from __future__ import annotations

from classifier import classify_indicator
from validation import has_substantive_content, is_section_header


# ── Classifier routing: Hindi provisions must shortlist the right indicator ──


def test_p6_1_hindi_transfer_abroad():
    text = "कोई भी व्यक्ति व्यक्तिगत डेटा को भारत के बाहर स्थानांतरित नहीं करेगा।"
    assert "6.1" in classify_indicator(text)


def test_p6_2_hindi_local_storage():
    text = "डेटा को देश के भीतर स्थानीय भंडारण में रखा जाएगा।"
    assert "6.2" in classify_indicator(text)


def test_p6_3_hindi_local_server():
    text = "प्रत्येक कंपनी भारत में एक सर्वर और डेटा केंद्र स्थापित करेगी।"
    assert "6.3" in classify_indicator(text)


def test_p6_4_hindi_conditional_transfer():
    text = "सीमापार अंतरण के लिए डेटा प्रधान की सहमति और पर्याप्त सुरक्षा आवश्यक है।"
    assert "6.4" in classify_indicator(text)


def test_p7_1_hindi_data_protection():
    text = "यह अधिनियम डिजिटल व्यक्तिगत डेटा संरक्षण और निजता के लिए है।"
    assert "7.1" in classify_indicator(text)


def test_p7_2_hindi_cybersecurity():
    text = "सरकार ने साइबर सुरक्षा और साइबर अपराध पर एक कानून बनाया।"
    assert "7.2" in classify_indicator(text)


def test_p7_3_hindi_retention_period():
    text = "डेटा को न्यूनतम अवधि के लिए प्रतिधारण किया जाएगा।"
    assert "7.3" in classify_indicator(text)


def test_p7_4_hindi_dpo():
    text = "प्रत्येक डेटा प्रत्ययी एक डेटा संरक्षण अधिकारी नियुक्त करेगा।"
    assert "7.4" in classify_indicator(text)


def test_p7_5_hindi_government_access():
    text = "सरकारी पहुंच और निगरानी राष्ट्रीय सुरक्षा के लिए विधि प्रवर्तन द्वारा।"
    assert "7.5" in classify_indicator(text)


# ── Validation gates: a real Hindi provision must not be dropped/misflagged ──


def test_hindi_provision_has_substantive_content():
    # करेगा (= "shall") is the operative marker; the English-only signal list
    # returned False before Devanagari markers were added.
    quote = "डेटा प्रत्ययी व्यक्तिगत डेटा संसाधित करने से पहले सहमति प्राप्त करेगा।"
    assert has_substantive_content(quote) is True


def test_hindi_provision_is_not_flagged_as_section_header():
    # Short Devanagari provision: the English short-label heading heuristic must
    # be skipped (via _NON_LATIN_RE) so it is not hard-rejected as a heading.
    quote = "डेटा प्रत्ययी सहमति प्राप्त करेगा।"
    assert is_section_header(quote) is False
