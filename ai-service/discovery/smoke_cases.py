"""Required-country positive-evidence cases shared by coverage and smoke checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SmokeCase:
    case_id: str
    country: str
    expected_title: str
    indicator: str
    aliases: tuple[str, ...]
    expected_ids: tuple[str, ...]
    required_evidence_markers: tuple[str, ...] = ()


# Negative conclusions remain manual and are intentionally excluded.
SMOKE_CASES = (
    SmokeCase("aus-local-processing-6.1", "AUS", "My Health Records Act", "6.1", ("My Health Records Act 2012",), ("C2012A00063",)),
    SmokeCase("aus-local-storage-6.2", "AUS", "My Health Records Act", "6.2", ("My Health Records Act 2012",), ("C2012A00063",)),
    SmokeCase("aus-conditional-flow-6.4", "AUS", "Privacy Act", "6.4", ("Privacy Act 1988",), ("C2004A03712",)),
    SmokeCase(
        "aus-binding-flow-agreement-6.5",
        "AUS",
        "Australia-Singapore Digital Economy Agreement",
        "6.5",
        ("Australia-Singapore Digital Economy Agreement",),
        ("australia-singapore-digital-economy-agreement",),
        (
            "article_23",
            "cross_border_transfer_information",
            "neither_party_shall_prohibit_or_restrict",
            "legitimate_public_policy_exception",
            "arbitrary_or_unjustifiable_discrimination",
            "no_greater_than_required",
        ),
    ),
    SmokeCase("aus-privacy-7.1", "AUS", "Privacy Act", "7.1", ("Privacy Act 1988",), ("C2004A03712",)),
    SmokeCase("aus-cyber-7.2", "AUS", "Cyber Security Act", "7.2", ("Cyber Security Act 2024",), ("C2024A00098",)),
    SmokeCase("aus-retention-7.3", "AUS", "Telecommunications (Interception and Access) Act", "7.3", ("Telecommunications (Interception and Access) Act 1979",), ("C2004A02124",)),
    SmokeCase("aus-pia-7.4", "AUS", "Privacy Act", "7.4", ("Privacy Act 1988",), ("C2004A03712",)),
    SmokeCase("aus-government-access-7.5", "AUS", "Telecommunications (Interception and Access) Act", "7.5", ("Telecommunications (Interception and Access) Act 1979",), ("C2004A02124",)),
    SmokeCase("mys-local-storage-6.2", "MYS", "Companies Act", "6.2", ("Companies Act 2016",), ("act-777",)),
    SmokeCase("mys-conditional-flow-6.4", "MYS", "Personal Data Protection Act", "6.4", ("Personal Data Protection Act 2010",), ("act-709",)),
    SmokeCase(
        "mys-binding-flow-agreement-6.5",
        "MYS",
        "Chapter 14 Electronic Commerce",
        "6.5",
        ("Chapter 14", "Electronic Commerce"),
        ("14._Electronic_Commerce_.pdf",),
        (
            "article_14_11",
            "cross_border_transfer_information",
            "each_party_shall_allow",
            "legitimate_public_policy_exception",
            "arbitrary_or_unjustifiable_discrimination",
            "no_greater_than_required",
        ),
    ),
    SmokeCase("mys-privacy-7.1", "MYS", "Personal Data Protection Act", "7.1", ("Personal Data Protection Act 2010",), ("act-709",)),
    SmokeCase("mys-cyber-7.2", "MYS", "Cyber Security Act", "7.2", ("Cyber Security Act 2024",), ("act-854",)),
    SmokeCase("mys-retention-7.3", "MYS", "Companies Act", "7.3", ("Companies Act 2016",), ("act-777",)),
    SmokeCase(
        "mys-dpo-statute-7.4",
        "MYS",
        "Personal Data Protection (Amendment) Act 2024",
        "7.4",
        ("Personal Data Protection (Amendment) Act 2024",),
        ("Act-A1727.pdf",),
        (
            "section_12a",
            "data_controller_shall_appoint_dpo",
            "data_processor_shall_appoint_dpo",
        ),
    ),
    SmokeCase(
        "mys-dpo-circular-7.4",
        "MYS",
        "Pelantikan Pegawai Perlindungan Data",
        "7.4",
        ("Appointment of Data Protection Officer", "Pelantikan Pegawai Perlindungan Data"),
        ("Pekeliling-DPO-1.pdf",),
        (
            "section_12a",
            "mandatory_dpo_appointment",
            "threshold_20000_data_subjects",
            "threshold_10000_sensitive_data_subjects",
            "regular_and_systematic_monitoring",
        ),
    ),
    SmokeCase("mys-government-access-7.5", "MYS", "Digital Signature Act", "7.5", ("Digital Signature Act 1997",), ("act-562",)),
    SmokeCase("sgp-conditional-flow-6.4", "SGP", "Personal Data Protection Act", "6.4", ("Personal Data Protection Act 2012",), ("PDPA2012",)),
    SmokeCase(
        "sgp-binding-flow-agreement-6.5",
        "SGP",
        "Australia-Singapore Digital Economy Agreement",
        "6.5",
        ("Australia-Singapore Digital Economy Agreement", "Singapore-Australia Digital Economy Agreement"),
        ("australia-singapore-digital-economy-agreement",),
        (
            "article_23",
            "cross_border_transfer_information",
            "neither_party_shall_prohibit_or_restrict",
            "legitimate_public_policy_exception",
            "arbitrary_or_unjustifiable_discrimination",
            "no_greater_than_required",
        ),
    ),
    SmokeCase("sgp-privacy-7.1", "SGP", "Personal Data Protection Act", "7.1", ("Personal Data Protection Act 2012",), ("PDPA2012",)),
    SmokeCase("sgp-cyber-7.2", "SGP", "Cybersecurity Act", "7.2", ("Cybersecurity Act 2018", "Cyber Security Act 2018"), ("CA2018",)),
    SmokeCase("sgp-retention-7.3", "SGP", "Companies Act", "7.3", ("Companies Act 1967",), ("CoA1967",)),
    SmokeCase("sgp-dpo-7.4", "SGP", "Personal Data Protection Act", "7.4", ("Personal Data Protection Act 2012",), ("PDPA2012",)),
    SmokeCase("sgp-government-access-7.5", "SGP", "Criminal Procedure Code", "7.5", ("Criminal Procedure Code 2010",), ("CPC2010",)),
)
