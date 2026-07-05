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
