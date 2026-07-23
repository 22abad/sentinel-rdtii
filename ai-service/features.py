"""Feature specifications per RDTII 2.1 indicator.

Each indicator's scoring rule (in `scoring/`) consumes a structured features dict.
The LLM provider's job is to read an article and emit these features —
nothing else. The deterministic scorer then applies the rule from the RDTII
2.1 guide to map features → score (0 / 0.5 / 1).

The `description` strings double as LLM prompt material: the provider injects
them into the extraction prompt so the LLM knows what to look for.

Sources:
- ESCAP RDTII 2.1 Guide, Chapter 3, Pillars 6 & 7
- Cross-checked against CHN-RDTII.xlsx (sample data)
"""

from __future__ import annotations

# Each indicator's spec maps feature_name -> (type_hint, description)
# Bespoke specs below cover the Round 1 pillars (6/7) plus indicators with
# hand-tuned scorers (2.1, 5.1, 5.3). Every other Round 2 indicator gets a
# methodology-driven generic spec from get_feature_spec() — see _generic_spec.
INDICATOR_FEATURES: dict[str, dict[str, dict[str, str]]] = {
    # Legacy Round 1 placeholder (1.1 is outside the Round 2 methodology; the
    # float-coercion regression test exercises it).
    "1.1": {"tariff_rate": {"type": "float", "description": "Applicable tariff rate"}},
    "2.1": {"procurement_preference": {"type": "bool", "description": "Local preference in procurement?"}},
    "5.1": {
        "has_competition": {
            "type": "bool",
            "description": "Does the provision show that competitive telecom market entry is allowed?",
        },
        "has_market_barrier": {
            "type": "bool",
            "description": "Does the provision impose telecom market entry barriers, exclusivity, or restrictive licensing?",
        },
        "no_license_needed": {
            "type": "bool",
            "description": "Does the provision state that no telecom service licence is required?",
        },
    },
    "5.3": {
        "government_equity_percentage": {
            "type": "float",
            "description": "Percentage of government equity/ownership in a domestic telecom operator (0–100).",
        },
        "has_government_owned_operator": {
            "type": "bool",
            "description": "Does the government hold any equity stake in a domestic telecom operator?",
        },
        "government_has_majority_stake": {
            "type": "bool",
            "description": "Does the government hold >50% equity stake in at least one telecom operator?",
        },
        "stake_percentage_raw": {
            "type": "str",
            "description": "Raw text describing government stake percentage or source reference.",
        },
        "partial_stake_desc": {
            "type": "str",
            "description": "Description of government stake if it is partial/not majority.",
        },
        "has_state_enterprise_role": {
            "type": "bool",
            "description": "Does a state-owned enterprise operate in the telecom sector?",
        },
        "operator_names": {
            "type": "str",
            "description": "Comma-separated names of telecom operators with government holdings.",
        },
    },
    "6.1": {
        "personal_data": {
            "type": "bool",
            "description": "Does the measure apply to personal data (name, ID, IP address, health, etc.)?",
        },
        "horizontal_scope": {
            "type": "bool",
            "description": "Does it apply across all sectors (horizontal), as opposed to a single sector?",
        },
        "has_ban": {
            "type": "bool",
            "description": "Does the measure impose an outright ban on cross-border data transfer?",
        },
        "has_local_processing": {
            "type": "bool",
            "description": "Does it require data to be processed within the country?",
        },
        "applies_to_government_data_only": {
            "type": "bool",
            "description": "Is the measure limited to government data only? (If true, indicator is excluded.)",
        },
        "num_economies_affected": {
            "type": "int",
            "description": "Number of foreign economies affected (1 = bilateral, 2+ = multilateral).",
        },
    },
    "6.2": {
        "personal_data": {"type": "bool", "description": "Applies to personal data?"},
        "horizontal_scope": {"type": "bool", "description": "Horizontal across all sectors?"},
        "has_local_storage": {
            "type": "bool",
            "description": "Mandates that a copy of certain data be stored within the country?",
        },
        "applies_to_government_data_only": {"type": "bool", "description": "Only government data?"},
    },
    "6.3": {
        "has_infrastructure_req": {
            "type": "bool",
            "description": "Mandates establishment of a local data centre / dedicated physical infrastructure?",
        },
        "applies_to_government_data_only": {"type": "bool", "description": "Only government data?"},
    },
    "6.4": {
        "personal_data": {"type": "bool", "description": "Applies to personal data?"},
        "horizontal_scope": {"type": "bool", "description": "Horizontal across all sectors?"},
        "has_conditional_flow": {
            "type": "bool",
            "description": "Imposes conditions on cross-border transfer (consent, adequacy, gov approval, SCC)?",
        },
    },
    "6.5": {
        "has_binding_agreement": {
            "type": "bool",
            "description": "Is the country signatory to a binding agreement on cross-border data flows (CPTPP, DEPA, RCEP Art. 12.15, etc.)?",
        },
    },
    "7.1": {
        "has_comprehensive_framework": {
            "type": "bool",
            "description": "Does the country have a comprehensive cross-sectoral data protection law?",
        },
        "has_sectoral_framework_only": {
            "type": "bool",
            "description": "Only sectoral data protection laws exist (no horizontal framework)?",
        },
    },
    "7.2": {
        "has_dedicated_cybersecurity_law": {
            "type": "bool",
            "description": "Dedicated horizontal cybersecurity legal framework exists?",
        },
        "has_sectoral_cybersecurity_only": {
            "type": "bool",
            "description": "Only sectoral or non-dedicated cybersecurity provisions?",
        },
    },
    "7.3": {
        "has_minimum_retention_period": {
            "type": "bool",
            "description": (
                "Does the text require records/data/documents to be RETAINED, "
                "PRESERVED, MAINTAINED or KEPT for a stated MINIMUM period — an "
                "explicit duration such as 'not less than 5 years', 'at least 3 "
                "years', 'for a period of N months/years', 'preserve for N "
                "years'? True only if a concrete minimum duration is stated. "
                "False for 'retain no longer than necessary' / data minimisation "
                "(that is not a minimum-retention rule)."
            ),
        },
        "applies_to_government_data_only": {"type": "bool", "description": "Only government data?"},
    },
    "7.4": {
        "has_dpo_requirement": {
            "type": "bool",
            "description": "Requires firms to appoint a Data Protection Officer (DPO)?",
        },
        "has_dpia_requirement": {
            "type": "bool",
            "description": "Requires firms to perform a Data Protection Impact Assessment (DPIA)?",
        },
        "horizontal_scope": {"type": "bool", "description": "Horizontal across all sectors?"},
    },
    "7.5": {
        "has_government_access_without_judicial_oversight": {
            "type": "bool",
            "description": "Allows government access to personal data without judicial warrant / independent oversight?",
        },
    },
}


def _generic_spec(indicator_id: str) -> dict[str, dict[str, str]]:
    """Build a methodology-driven spec for indicators without a bespoke one.

    The LLM extracts *which official criterion* the provision matches — a
    categorical fact checkable against the published criteria — never a
    numeric score. scoring/generic.py maps the criterion to its published
    score deterministically.
    """

    from methodology import get_rule

    rule = get_rule(indicator_id)
    if rule is None:
        return {}
    # Keep descriptions single-line: they are injected into an indented
    # prompt list, where embedded newlines garble the structure.
    category = " ".join(rule.category.split())
    numbered = " | ".join(f"[{i}] {' '.join(opt.split())}" for i, opt in enumerate(rule.options, 1))
    spec: dict[str, dict[str, str]] = {
        "measure_present": {
            "type": "bool",
            "description": (
                f"true ONLY if the provision itself ESTABLISHES a binding measure/"
                f"requirement concerning: {category}. false if the text merely "
                "relates to the topic, grants a general power, or describes "
                "policy without imposing the measure."
            ),
        },
        "matched_criterion": {
            "type": "int",
            "description": (
                "The official RDTII criterion whose conditions the quoted text "
                f"EXPLICITLY satisfies, from: {numbered}. Calibration: choose the "
                "LOWEST-scoring criterion consistent with the quote; topical "
                "relevance alone is not a measure; statements of principle, "
                "objectives or general policy are NOT measures (legal review: "
                "every adjudicated over-score quoted a principles provision); "
                "if the text only provides a legal basis or power without the "
                "actual measure, or you are unsure, answer 0."
            ),
        },
    }
    if rule.counting_step is not None:
        spec["measure_count"] = {
            "type": "int",
            "description": (
                "Number of DISTINCT qualifying measures evidenced in the "
                "provision (each must be separately identifiable)."
            ),
        }
    return spec


def get_feature_spec(indicator_id: str) -> dict[str, dict[str, str]]:
    """Return the feature spec for an indicator, or empty dict if unknown.

    Bespoke specs win; all other Round 2 indicators fall back to the
    methodology-driven generic spec.
    """
    spec = INDICATOR_FEATURES.get(indicator_id)
    if spec:
        return spec
    return _generic_spec(indicator_id)


def list_supported_indicators() -> list[str]:
    """Return all indicator IDs the system can handle."""
    from methodology import load_methodology

    ids = set(INDICATOR_FEATURES) | set(load_methodology())
    return sorted(ids, key=lambda x: [int(p) for p in x.split(".")])
