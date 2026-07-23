"""Cross-language NEW/KNOWN reconciliation by statute number + year."""
from submission.novelty import law_number_key, is_known_law, known_law_index


def test_law_number_key_extraction():
    assert law_number_key("UU No. 27 Tahun 2022 — Pelindungan Data Pribadi") == "27/2022"
    assert law_number_key("Law No. 27 on Personal Data Protection 2022") == "27/2022"
    assert law_number_key("Regulation of the Minister of Trade No.34/M-DAG/PER/6/2014") == "34/2014"
    # No statute number -> no key (name matching still applies).
    assert law_number_key("Digital Personal Data Protection Act 2023") is None
    assert law_number_key("") is None


def test_indonesian_native_title_reconciles_to_english_baseline():
    # UU 27/2022 (the PDP Law) IS in the Round-2 baseline under its English
    # name; a native-title discovery must be KNOWN, not NEW.
    idx = known_law_index()
    assert is_known_law("IDN", "UU No. 27 Tahun 2022 — Pelindungan Data Pribadi", idx)


def test_number_not_in_baseline_stays_new():
    idx = known_law_index()
    # A fabricated number+year that no baseline law carries stays NEW.
    assert not is_known_law("IDN", "Peraturan Fiktif No. 9999 Tahun 3021", idx)
