"""Filename-stage country detection — the only signal an image-only scanned
PDF has before OCR (the browser parses it to zero text, so the canvas prepare
path reaches detection with an empty body)."""

from country_detector import detect_country, detect_country_from_filename


def test_filename_iso3_prefix_detects():
    r = detect_country_from_filename("MYS_Pekeliling_scanned_demo.pdf")
    assert r["code"] == "MYS"
    assert r["confidence"] >= 0.8


def test_filename_iso3_lowercase_and_hyphens():
    r = detect_country_from_filename("aus-cyber-security-act-2024.pdf")
    assert r["code"] == "AUS"


def test_filename_full_country_name():
    r = detect_country_from_filename("singapore pdpa consolidated.pdf")
    assert r["code"] == "SGP"


def test_filename_no_signal():
    r = detect_country_from_filename("scanned_document_final_v2.pdf")
    assert r["code"] is None


def test_filename_is_last_resort_after_text():
    # Real text keywords must beat the filename hint.
    r = detect_country(
        text="Akta Perlindungan Data Peribadi 2010 " * 5,
        filename="AUS_mislabeled.pdf",
    )
    assert r["code"] == "MYS"


def test_empty_text_falls_back_to_filename():
    r = detect_country(text="", filename="MYS_Pekeliling_scanned_demo.pdf")
    assert r["detected"] is True
    assert r["code"] == "MYS"
    assert "filename" in r["source"]


def test_word_boundary_no_false_positive():
    # "pausing" contains "aus" but not as a token — must not detect.
    r = detect_country_from_filename("pausing_regulation_review.pdf")
    assert r["code"] is None
