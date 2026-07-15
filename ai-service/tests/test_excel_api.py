from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook

import main as main_module


def test_excel_export_returns_rdtii_workbook():
    client = TestClient(main_module.app)

    response = client.post(
        "/api/excel/export",
        json={
            "country": "SGP",
            "filename": "rdtii_test.xlsx",
            "mappings": [
                {
                    "pillar": 6,
                    "indicator": "6.1",
                    "score": 0.5,
                    "verbatim_quote": "An organisation may transfer personal data outside Singapore.",
                    "quote_start": 0,
                    "quote_end": 61,
                    "article_clause": "Section 26",
                    "source_legislation": "Personal Data Protection Act 2012",
                    "last_update": "2020-10-01",
                    "source_url": "https://sso.agc.gov.sg/Act/PDPA2012",
                    "scope": "horizontal",
                    "features": {"has_cross_border_transfer_rule": True},
                    "impact": "Cross-border transfer rule identified.",
                    "coverage": "Personal data transfers",
                    "cluster": "Digital governance policies",
                    "region": "South-East Asia",
                    "cov_name": "Cross-cutting",
                    "name": "Cross-border data policies",
                    "policy_description": "Personal data transfer restrictions",
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.headers["content-disposition"] == 'attachment; filename="rdtii_test.xlsx"'

    workbook = load_workbook(BytesIO(response.content))
    worksheet = workbook.active
    headers = [cell.value for cell in worksheet[1]]
    assert headers == [
        "Pillar",
        "Indicator",
        "Score",
        "Act and/or practice",
        "Coverage",
        "Impacts or comments",
        "Timeframe",
        "Reference (URL)",
        "Verbatim Quote",
        "Provision Article",
        "Source Validation",
    ]
    assert worksheet["A2"].value == "Pillar 6"
    assert worksheet["B2"].value == "6.1"
    assert worksheet["D2"].value == "Personal Data Protection Act 2012"


def _mapping(indicator, quote, *, pillar):
    return {
        "pillar": pillar,
        "indicator": indicator,
        "score": 1.0,
        "verbatim_quote": quote,
        "quote_start": 0,
        "quote_end": len(quote),
        "source_legislation": "Personal Data Protection Act 2012",
        "source_url": "https://sso.agc.gov.sg/Act/PDPA2012",
    }


_STRONG = _mapping(
    "6.4",
    "An organisation must not transfer any personal data to a country or "
    "territory outside Singapore except in accordance with this Act.",
    pillar=6,
)
_WEAK_TITLE = _mapping("7.5", "Personal Data Protection Act 2012", pillar=7)  # non-framework title-quote


def _rows(content):
    workbook = load_workbook(BytesIO(content))
    ws = workbook.active
    return list(ws.iter_rows(min_row=2, values_only=True))


def test_export_keeps_all_rows_by_default():
    client = TestClient(main_module.app)
    resp = client.post(
        "/api/excel/export",
        json={"country": "SGP", "mappings": [_STRONG, _WEAK_TITLE]},
    )
    assert resp.status_code == 200
    # Default (drop_weak absent) exports exactly what it was given — both rows.
    assert len(_rows(resp.content)) == 2


def test_drop_weak_filters_weak_evidence_rows():
    client = TestClient(main_module.app)
    resp = client.post(
        "/api/excel/export",
        json={"country": "SGP", "mappings": [_STRONG, _WEAK_TITLE], "drop_weak": True},
    )
    assert resp.status_code == 200
    rows = _rows(resp.content)
    # The weak non-framework title-quote is dropped; the strong provision stays.
    assert len(rows) == 1
    assert rows[0][1] == "6.4"
