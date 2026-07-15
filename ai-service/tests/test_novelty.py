from __future__ import annotations

from submission.novelty import (
    build_discovery_report,
    is_known_law,
    known_law_index,
    load_known_inventory,
    normalize_article,
    normalize_law_name,
    normalized_quote_hash,
    reconcile_discovery_tags,
    reconcile_submission_tags,
    summarize_discovery,
)
from submission.schema import SubmissionRow


def test_official_inventory_loads_and_covers_three_economies():
    inv = load_known_inventory()
    assert len(inv) > 150  # ~195 distinct KNOWN laws
    economies = {econ for econ, _ in inv}
    assert economies == {"AUS", "MYS", "SGP"}
    # A representative KNOWN law from the official ESCAP inventory.
    assert ("MYS", normalize_law_name("Personal Data Protection Act 2010")) in inv


def _row(economy, law_name, indicator_id="P6-I1", tag="NEW", **kw):
    return SubmissionRow(
        economy=economy,
        law_name=law_name,
        indicator_id=indicator_id,
        verbatim_snippet=kw.get("verbatim_snippet", "…"),
        discovery_tag=tag,
        source_url=kw.get("source_url", "https://example.gov/x"),
        article=kw.get("article", ""),
        last_amended=kw.get("last_amended", ""),
        amendment_version_date=kw.get("amendment_version_date", ""),
        retrieval_method=kw.get("retrieval_method", "official_search"),
    )


def test_normalize_drops_year_number_and_punctuation():
    assert normalize_law_name("Companies Act 2016 (Act 777)") == "companies act"
    assert normalize_law_name("Personal Data Protection Act 2012") == "personal data protection act"
    assert normalize_law_name("My Health Records Act 2012") == "my health records act"


def test_normalize_strips_country_prefix_and_bare_act_number():
    # Live discovery emits verbose titles: a leading country word and a bare
    # statute number ("No. 709") must not create a distinct identity from the
    # curated "Personal Data Protection Act".
    canonical = "personal data protection act"
    assert normalize_law_name("Malaysia Personal Data Protection Act (PDPA), 2010, No. 709") == canonical
    assert normalize_law_name("Singapore Personal Data Protection Act (PDPA), 2012, No. 26") == canonical
    assert normalize_law_name("PERSONAL DATA PROTECTION ACT 2010") == canonical
    # A leading "Chapter N" is number noise too.
    assert normalize_law_name("Chapter 14 Electronic Commerce") == "electronic commerce"
    # A bare "Act" with no number is part of the title and must be kept.
    assert normalize_law_name("Communications and Multimedia Act (Act 588) 1998") == (
        "communications and multimedia act"
    )


def test_normalize_strips_dash_jurisdiction_suffix_but_not_bare_country_word():
    # The ESCAP inventory tags multilateral instruments "... - Malaysia"; a
    # discovery title carries no such suffix, so both must reconcile.
    cptpp = "comprehensive and progressive agreement for trans pacific partnership"
    assert normalize_law_name("Comprehensive And Progressive Agreement For Trans-Pacific Partnership - Malaysia") == cptpp
    assert normalize_law_name("Viet Nam Comprehensive and Progressive Agreement for Trans-Pacific Partnership (CPTPP), 2018") == cptpp
    # A statute whose title genuinely ends in a country word (no dash) is kept.
    assert normalize_law_name("Bank Negara Malaysia") == "bank negara malaysia"
    assert normalize_law_name("Standards of Malaysia Act (Act 549) 1996") == "standards of malaysia act"


def test_classify_new_candidate_triages_noise_and_leads():
    import re as _re

    from submission.novelty import classify_new_candidate

    topical = _re.compile(r"privacy|personal data|identity verificat|cyber", _re.I)

    def verdict(name, url, quote="", econ="AUS"):
        cand = {"law_name": name, "source_url": url, "verbatim_snippet": quote}
        return classify_new_candidate(cand, economy_code=econ, topical=topical)[0]

    # International instruments are not domestic statutes.
    assert verdict("Singapore-Australia Free Trade Agreement", "https://legislation.gov.au/x") == "REJECT"
    assert verdict("Western Australia Pasture Seeds Levy Agreement", "https://legislation.gov.au/x") == "REJECT"
    # A foreign law name served from this economy's own official domain = mislabel.
    assert verdict("Hong Kong Personal Data (Privacy) Ordinance", "https://lom.agc.gov.my/act", econ="MYS") == "REJECT"
    # Off-topic domestic legislation (no pillar vocabulary in name or quote).
    assert verdict("Primary Industries (Customs) Charges Regulations 2024",
                   "https://legislation.gov.au/x", quote="Wine Export Charge") == "REJECT"
    # A genuine on-topic domestic statute on an official domain is a lead.
    assert verdict("Identity Verification Services Act 2023",
                   "https://legislation.gov.au/C2023A00123") == "CANDIDATE"
    # On-topic but off an official domain needs a provenance check.
    assert verdict("Some Data Privacy Rules", "https://random-blog.example.com/x") == "REVIEW"

    # A NEW_PROVISION of an already-KNOWN law is not a new-law discovery — it is
    # also the shape of the LLM mislabelling a quote from one statute with a
    # different known statute's name (a PDPA name on a Financial Services Act
    # URL). It must be demoted from CANDIDATE to REVIEW.
    from submission.novelty import classify_new_candidate
    prov = {"law_name": "Personal Data Protection Act 2012",
            "source_url": "https://sso.agc.gov.sg/Act/FSA1993",
            "verbatim_snippet": "personal data", "novelty_type": "NEW_PROVISION"}
    assert classify_new_candidate(prov, economy_code="SGP", topical=topical)[0] == "REVIEW"


def test_false_new_suppressed_but_genuine_new_preserved():
    # The economy's own flagship statute — however the LLM verbosely titles it,
    # including foreign-relabelled hallucinations of a Malaysia document — must
    # reconcile to KNOWN, not be paraded as a NEW discovery.
    index = known_law_index()
    assert is_known_law("Malaysia", "Malaysia Personal Data Protection Act (PDPA), 2010, No. 709", index)
    assert is_known_law("Malaysia", "Singapore Personal Data Protection Act (PDPA), 2012, No. 26", index)
    # Genuine independent finds stay NEW after the stronger normalization.
    assert not is_known_law("Singapore", "Spam Control Act 2007", index)
    assert not is_known_law("Australia", "Identity Verification Services Act 2023", index)


def test_round2_baseline_wired_with_bilingual_and_split_acts():
    # The seven Round 2 economies must have a KNOWN baseline (from the Round 2
    # Database inventory), else every discovered law is spuriously NEW.
    index = known_law_index()
    for code in ("CHN", "IND", "IDN", "LAO", "MNG", "RUS", "THA"):
        assert any(k[0] == code for k in index), f"no Round 2 baseline for {code}"
    # Bilingual titles reconcile from the English name alone...
    assert is_known_law("China", "Cybersecurity Law of the People's Republic of China", index)
    assert is_known_law("China", "Personal Information Protection Law of the People's Republic of China", index)
    # ...and from the native-script original alone.
    assert is_known_law("China", "中华人民共和国网络安全法", index)
    # Acts concatenated into one inventory cell are split and each is KNOWN.
    assert is_known_law("China", "Measures for Cybersecurity Review", index)
    # A law absent from every baseline is still NEW.
    assert not is_known_law("China", "Zzz Nonexistent Data Localization Act 2099", index)


def test_inventory_identity_keys_splits_and_delanguages():
    from submission.novelty import _inventory_identity_keys

    raw = ("Cybersecurity Law of the People's Republic of China《中华人民共和国网络安全法》;\n\n"
           "Measures for Cybersecurity Review《网络安全审查办法》")
    keys = _inventory_identity_keys("CHN", raw)
    normed = {k[1] for k in keys}
    assert "cybersecurity law of the people s republic of china" in normed  # English-only
    assert "measures for cybersecurity review" in normed                    # split second act
    assert "中华人民共和国网络安全法" in normed                                 # native-script only
    assert all(k[0] == "CHN" for k in keys)


def test_known_index_matches_baseline_and_rejects_unseen():
    index = known_law_index()
    # Laws in the KNOWN baseline (library), across title variants.
    assert is_known_law("Malaysia", "Companies Act 2016 (Act 777)", index)
    assert is_known_law("SGP", "Personal Data Protection Act 2012", index)
    assert is_known_law("Australia", "Privacy Act 1988", index)
    # Laws only in the official ESCAP Legal Inventory are also KNOWN.
    assert is_known_law("Singapore", "Cybersecurity Act 2018", index)
    assert is_known_law("Australia", "Security of Critical Infrastructure Act 2018", index)
    # A law in neither the library nor the official inventory is not KNOWN.
    assert not is_known_law("Singapore", "Zzz Data Localisation Act 2099", index)
    # Right law, wrong economy -> not KNOWN.
    assert not is_known_law("Australia", "Companies Act 2016 (Act 777)", index)


def test_reconcile_flips_tags_from_the_baseline():
    rows = [
        _row("Malaysia", "Companies Act 2016 (Act 777)", "P7-I3", tag="NEW"),  # actually KNOWN
        _row("Singapore", "Zzz Data Localisation Act 2099", "P6-I5", tag="KNOWN"),  # actually NEW
    ]
    reconciled = reconcile_discovery_tags(rows)
    by_law = {r.law_name: r.discovery_tag for r in reconciled}
    assert by_law["Companies Act 2016 (Act 777)"] == "KNOWN"
    assert by_law["Zzz Data Localisation Act 2099"] == "NEW"
    # Reconciliation is immutable — inputs untouched.
    assert rows[0].discovery_tag == "NEW"


def test_reconcile_distinguishes_law_amendment_provision_and_known_evidence():
    known_quote = (
        "An organisation must not transfer any personal data to a country or "
        "territory outside Singapore except in accordance with requirements "
        "prescribed under this Act to ensure that organisations provide a standard "
        "of protection to personal data so transferred that is comparable to the "
        "protection under this Act."
    )
    rows = [
        _row(
            "Singapore",
            "Personal Data Protection Act 2012",
            article="Section 26",
            verbatim_snippet=known_quote,
            amendment_version_date="2025-12-05",
        ),
        _row(
            "Singapore",
            "Personal Data Protection Act 2012",
            article="Section 27A",
            verbatim_snippet="A newly inserted provision.",
        ),
        _row(
            "Singapore",
            "Personal Data Protection Act 2012",
            article="Section 26",
            verbatim_snippet=known_quote,
            amendment_version_date="2027-01-01",
        ),
        _row(
            "Australia",
            "Privacy Act 1988",
            article="Australian Privacy Principle 8.1",
            verbatim_snippet="Existing provision in a newly numbered compilation.",
            amendment_version_date="Compilation No. 105",
        ),
        _row("Singapore", "Zzz Data Localisation Act 2099"),
    ]

    reconciled = reconcile_discovery_tags(rows)

    assert [row.novelty_type for row in reconciled] == [
        "KNOWN", "NEW_PROVISION", "NEW_AMENDMENT", "NEW_AMENDMENT", "NEW_LAW",
    ]
    assert [row.discovery_tag for row in reconciled] == [
        "KNOWN", "NEW", "NEW", "NEW", "NEW",
    ]
    assert reconciled[0].canonical_law_id == "sgp-pdpa-2012"
    assert reconciled[1].normalized_article == "section 27a"
    assert reconciled[1].normalized_quote_hash == normalized_quote_hash(
        "A newly inserted provision."
    )


def test_submission_tags_remain_law_level_with_detailed_novelty_metadata():
    rows = [
        _row(
            "Singapore",
            "Cybersecurity Act 2018",
            article="Section 99A",
            verbatim_snippet="A newly discovered provision.",
        ),
        _row(
            "Singapore",
            "Unseen Fixture Act 2099",
            retrieval_method="fixture",
        ),
        _row("Singapore", "Zzz Data Localisation Act 2099"),
    ]

    reconciled = reconcile_submission_tags(rows)

    assert [row.discovery_tag for row in reconciled] == ["KNOWN", "KNOWN", "NEW"]
    assert reconciled[0].novelty_type == "NEW_PROVISION"
    assert reconciled[2].novelty_type == "NEW_LAW"


def test_evidence_normalization_is_stable():
    assert normalize_article("Sec. 26(2)") == normalize_article("Section 26 (2)")
    assert normalized_quote_hash("Data must stay here.") == normalized_quote_hash(
        " data MUST stay here "
    )
    assert normalized_quote_hash("Данные должны храниться здесь") != normalized_quote_hash(
        "Другой текст"
    )


def test_reconcile_never_labels_fixture_sources_new():
    fixture = _row(
        "Singapore",
        "Unseen Fixture Act 2099",
        tag="NEW",
    ).model_copy(update={"retrieval_method": "fixture"})
    fallback = fixture.model_copy(
        update={"law_name": "Unseen Fallback Act 2099", "retrieval_method": "fallback"}
    )

    reconciled = reconcile_discovery_tags([fixture, fallback])

    assert [row.discovery_tag for row in reconciled] == ["KNOWN", "KNOWN"]


def test_report_lists_new_candidates_with_audit_and_gate():
    rows = [
        _row("Singapore", "Personal Data Protection Act 2012", "P6-I4", tag="NEW"),  # KNOWN baseline
        _row(
            "Singapore",
            "Zzz Data Localisation Act 2099",
            "P6-I5",
            tag="NEW",
            source_url="https://sso.agc.gov.sg/Act/ZZZ2099",
            verbatim_snippet="data must be stored locally…",
        ),
    ]
    report = build_discovery_report("Singapore", rows)
    summary = report["summary"]
    assert summary["total_provisions"] == 2
    assert summary["new_provisions"] == 1
    assert summary["known_provisions"] == 1
    assert summary["novelty_types"] == {
        "KNOWN": 1,
        "NEW_LAW": 1,
        "NEW_AMENDMENT": 0,
        "NEW_PROVISION": 0,
    }
    assert summary["new_laws"] == [
        {"economy": "Singapore", "law_name": "Zzz Data Localisation Act 2099", "indicators": ["P6-I5"]}
    ]
    # NEW candidate carries the audit trail for the human gate.
    assert report["new_candidates"][0]["source_url"] == "https://sso.agc.gov.sg/Act/ZZZ2099"
    assert report["new_candidates"][0]["novelty_type"] == "NEW_LAW"
    assert "draft lead for legal review" in report["review_gate"]


def test_summary_groups_indicators_per_law():
    rows = [
        _row("Australia", "My Health Records Act 2012", "P6-I1", tag="KNOWN"),
        _row("Australia", "My Health Records Act 2012", "P6-I2", tag="KNOWN"),
    ]
    summary = summarize_discovery(reconcile_discovery_tags(rows))
    assert summary["known_laws"] == [
        {
            "economy": "Australia",
            "law_name": "My Health Records Act 2012",
            "indicators": ["P6-I1", "P6-I2"],
        }
    ]
