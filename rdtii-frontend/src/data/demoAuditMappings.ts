import type { ExtractionResponse } from "../types";

export const demoAuditExtraction: ExtractionResponse = {
  provider: "demo/rdtii-fixture",
  source_text: `Personal Data Protection Act 2012, Section 26: An organisation shall not transfer any personal data to a country or territory outside Singapore except in accordance with requirements prescribed under this Act.

Personal Data Protection Regulations 2021, Regulation 11: An organisation must develop and implement policies and practices necessary for it to meet its obligations under the Act.

Cybersecurity Act 2018, Section 15: The owner of a critical information infrastructure must comply with codes and directions issued by the Commissioner.`,
  rejected: [],
  mappings: [
    {
      pillar: 6,
      indicator: "6.1",
      score: 0.5,
      verbatim_quote:
        "An organisation shall not transfer any personal data to a country or territory outside Singapore except in accordance with requirements prescribed under this Act.",
      quote_start: 43,
      quote_end: 190,
      article_clause: "Section 26",
      source_legislation: "Personal Data Protection Act 2012",
      last_update: "2021-02-01",
      source_url: "https://sso.agc.gov.sg/Act/PDPA2012",
      scope: "horizontal",
      coverage: "Personal data transfers by organisations",
      cluster: "Digital governance policies",
      region: "South-East Asia",
      cov_name: "Cross-cutting",
      name: "Cross-border data policies",
      policy_description: "Restrictions or conditions on cross-border transfer of personal data",
      features: {
        has_cross_border_transfer_rule: true,
        requires_transfer_protection: true,
        unrestricted_transfer: false,
        _source_grade: "primary",
        _timeframe_column: "Since February 2021",
      },
      impact:
        "Singapore permits cross-border transfers only when prescribed protection requirements are met, creating a conditional transfer regime.",
      requires_human_review: false,
      flag_reasons: [],
      extraction_provider: "demo/rdtii-fixture",
      timestamp_verification: {
        verified: true,
        best_date: "2021-02-01",
      },
    },
    {
      pillar: 7,
      indicator: "7.3",
      score: 1,
      verbatim_quote:
        "An organisation must develop and implement policies and practices necessary for it to meet its obligations under the Act.",
      quote_start: 247,
      quote_end: 362,
      article_clause: "Regulation 11",
      source_legislation: "Personal Data Protection Regulations 2021",
      last_update: "2021-02-01",
      source_url: "https://sso.agc.gov.sg/SL/PDPA2012-S63-2021",
      scope: "horizontal",
      coverage: "Personal data governance policies and practices",
      cluster: "Digital governance policies",
      region: "South-East Asia",
      cov_name: "Cross-cutting",
      name: "Domestic data protection",
      policy_description: "Internal governance and accountability requirements for data protection",
      features: {
        requires_data_protection_policy: true,
        requires_privacy_management_programme: true,
        _source_grade: "primary",
        _timeframe_column: "Since February 2021",
      },
      impact:
        "The regulation requires organisations to maintain policies and practices supporting data protection compliance.",
      requires_human_review: false,
      flag_reasons: [],
      extraction_provider: "demo/rdtii-fixture",
      timestamp_verification: {
        verified: true,
        best_date: "2021-02-01",
      },
    },
    {
      pillar: 7,
      indicator: "7.5",
      score: 0.5,
      verbatim_quote:
        "The owner of a critical information infrastructure must comply with codes and directions issued by the Commissioner.",
      quote_start: 388,
      quote_end: 496,
      article_clause: "Section 15",
      source_legislation: "Cybersecurity Act 2018",
      last_update: "2018-08-31",
      source_url: "https://sso.agc.gov.sg/Act/CA2018",
      scope: "sectoral",
      coverage: "Critical information infrastructure owners",
      cluster: "Digital governance policies",
      region: "South-East Asia",
      cov_name: "Sectoral",
      name: "Cybersecurity obligations",
      policy_description: "Security duties for critical information infrastructure",
      features: {
        has_security_obligations: true,
        applies_to_all_data_controllers: false,
        _source_grade: "primary",
        _timeframe_column: "Since August 2018",
      },
      impact:
        "Cybersecurity duties exist for designated critical infrastructure, but the obligation is sectoral rather than economy-wide.",
      requires_human_review: true,
      flag_reasons: ["Sectoral scope should be confirmed by a reviewer before final scoring."],
      extraction_provider: "demo/rdtii-fixture",
      timestamp_verification: {
        verified: true,
        best_date: "2018-08-31",
      },
    },
  ],
};
