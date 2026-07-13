from __future__ import annotations

from discovery.dedupe import dedupe_candidates
from discovery.schemas import LegalCandidate


def test_duplicate_urls_collapse_and_merge_indicator_matches():
    first = LegalCandidate(
        id="one",
        country_code="SGP",
        title="Personal Data Protection Act 2012",
        url="https://sso.agc.gov.sg/Act/PDPA2012?utm_source=test",
        source_domain="sso.agc.gov.sg",
        matched_indicators=["7.1"],
        matched_pillars=[7],
        reasons=["official source domain"],
    )
    duplicate = LegalCandidate(
        id="two",
        country_code="SGP",
        title="Personal Data Protection Act 2012",
        url="https://sso.agc.gov.sg/Act/PDPA2012",
        source_domain="sso.agc.gov.sg",
        matched_indicators=["6.4"],
        matched_pillars=[6],
        reasons=["matches indicator 6.4 terms"],
    )

    deduped = dedupe_candidates([first, duplicate])

    assert len(deduped) == 1
    assert deduped[0].matched_indicators == ["6.4", "7.1"]
    assert deduped[0].matched_pillars == [6, 7]
    assert "duplicate candidate merged" in deduped[0].reasons


def test_duplicate_external_ids_collapse_across_url_variants():
    thai = LegalCandidate(
        id="thai",
        country_code="THA",
        title="พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล",
        url="https://searchlaw.ocs.go.th/council-of-state/#/public/doc/pdpa-2562",
        source_domain="searchlaw.ocs.go.th",
        source_adapter="thailand_ocs",
        external_id="pdpa-2562",
        language="th",
        snippet="short",
        matched_indicators=["7.1"],
        matched_pillars=[7],
    )
    english = LegalCandidate(
        id="english",
        country_code="THA",
        title="Personal Data Protection Act B.E. 2562",
        url="https://searchlaw.ocs.go.th/council-of-state/#/public/doc/pdpa-2562?lang=en",
        source_domain="searchlaw.ocs.go.th",
        source_adapter="thailand_ocs",
        external_id="pdpa-2562",
        language="en",
        last_update="2019-05-27",
        snippet="longer English snippet with cross-border transfer details",
        matched_indicators=["6.4"],
        matched_pillars=[6],
    )

    deduped = dedupe_candidates([thai, english])

    assert len(deduped) == 1
    assert deduped[0].matched_indicators == ["6.4", "7.1"]
    assert deduped[0].matched_pillars == [6, 7]
    assert deduped[0].last_update == "2019-05-27"
    assert deduped[0].snippet == "longer English snippet with cross-border transfer details"
