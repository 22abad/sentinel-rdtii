from __future__ import annotations

import importlib.util
from pathlib import Path


TOOL = Path(__file__).resolve().parents[2] / "tools" / "review_verdicts_to_golden.py"
SPEC = importlib.util.spec_from_file_location("review_verdicts_to_golden", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_reassign_creates_old_negative_and_new_positive():
    quote = (
        "An organisation must not transfer any personal data to a country or territory "
        "outside Singapore except in accordance with requirements prescribed under this "
        "Act to ensure that organisations provide a standard of protection to personal "
        "data so transferred that is comparable to the protection under this Act."
    )
    export = {
        "reviewer": "Law student",
        "decisions": [{
            "verdict": "reassign",
            "law_name": "Personal Data Protection Act 2012",
            "engine_indicator": "P6-I1",
            "reviewer_indicators": ["P6-I4"],
            "verbatim_quote": quote,
            "article": "Section 26",
            "note": "Conditional safeguard, not an absolute ban.",
        }],
    }
    cases, warnings = MODULE.convert_document(export)
    assert warnings == []
    assert {(case["indicator_id"], case["should_map"]) for case in cases} == {
        ("6.1", False), ("6.4", True),
    }
    assert all(case["review"]["status"] == "pending" for case in cases)
