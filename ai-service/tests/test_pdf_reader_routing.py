from __future__ import annotations

from pdf_reader import _page_needs_ocr


def test_decorative_image_does_not_force_ocr_when_text_layer_is_complete():
    text = "Personal Data Protection Act section obligations. " * 5

    assert _page_needs_ocr(text, has_images=True) is False


def test_image_page_with_no_text_layer_still_requires_ocr():
    assert _page_needs_ocr("", has_images=True) is True
