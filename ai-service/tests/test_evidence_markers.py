from discovery.evidence_markers import match_evidence_markers


def test_treaty_evidence_markers_require_operational_clause_and_exception_guardrails():
    text = """
    ARTICLE 14.11: Cross-Border Transfer of Information by Electronic Means
    Each Party shall allow the cross-border transfer of information by electronic means.
    A measure may achieve a legitimate public policy objective if it is not arbitrary or
    unjustifiable discrimination and does not impose restrictions greater than are required.
    """

    assert set(match_evidence_markers(text)) >= {
        "article_14_11",
        "cross_border_transfer_information",
        "each_party_shall_allow",
        "legitimate_public_policy_exception",
        "arbitrary_or_unjustifiable_discrimination",
        "no_greater_than_required",
    }


def test_malaysia_dpo_markers_support_english_statute_and_malay_thresholds():
    text = """
    Section 12A. A data controller shall appoint one or more data protection officers.
    A data processor shall appoint one or more data protection officers.
    Keperluan mandatori bagi pelantikan pegawai perlindungan data.
    Pengawal data dan pemproses data hendaklah melantik seorang atau lebih pegawai
    perlindungan data jika data peribadi melebihi 20,000 bilangan subjek data;
    data peribadi sensitif melebihi 10,000 bilangan subjek data; atau aktiviti yang
    memerlukan pemantauan berkala dan sistematik.
    """

    assert set(match_evidence_markers(text)) >= {
        "section_12a",
        "data_controller_shall_appoint_dpo",
        "data_processor_shall_appoint_dpo",
        "mandatory_dpo_appointment",
        "threshold_20000_data_subjects",
        "threshold_10000_sensitive_data_subjects",
        "regular_and_systematic_monitoring",
    }


def test_section_12a_marker_tolerates_pdf_character_spacing():
    assert "section_12a" in match_evidence_markers("12 A . (1) A data controller shall appoint")
