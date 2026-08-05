"""Tests for the RLVR dataset-lab renderer (stn_cli.rlvr_render).

These pin the two things a measurement view can get wrong in a way that misleads
rather than merely looks bad:

  * **absent rendered as zero** — the offline and --with-llm reports carry
    different fields, so a missing metric shown as 0.000 makes a stale or
    partial report read as a catastrophic one;
  * **the pass line** — 0.9 hygiene top-1 is the harness's own gate on wiring
    best-of-N, so the green/red tint is a verdict, not decoration.

`_plain` strips markup so we can assert the human-readable result too.
"""

from __future__ import annotations

from rich.text import Text

from stn_cli.rlvr_render import (
    CASE_COLUMNS,
    PASS_LINE,
    case_row,
    num,
    pct,
    render_by_kind,
    render_case,
    render_components,
    render_config,
    render_header,
    render_headline,
    render_history,
    render_sections,
    render_summary,
    short_commit,
    signed,
)


def _plain(markup: str) -> str:
    return Text.from_markup(markup).plain


# ── scalars: absent must never look like zero ────────────────────────────


def test_pct_formats_a_rate():
    assert pct(0.9375) == "93.75%"
    assert pct(1.0) == "100.00%"


def test_pct_of_missing_is_na_not_zero():
    assert pct(None) == "n/a"
    assert pct("") == "n/a"


def test_num_of_missing_is_na_not_zero():
    assert num(None) == "n/a"
    assert num(0.8676, 4) == "0.8676"


def test_signed_keeps_the_sign():
    assert signed(0.042) == "+0.0420"
    assert signed(-0.1905) == "-0.1905"
    assert signed(None) == "n/a"


def test_short_commit():
    assert short_commit("708976b2356fba021b3514a58ef52f0beab67abd") == "708976b"
    assert short_commit(None) == "–"


# ── header: which run am I looking at, and did it cost money ─────────────


def test_offline_header_says_free():
    out = render_header({"mode": "offline-synthetic-distractors", "llm_provider": None})
    assert "offline, free" in _plain(out)
    assert "billed" not in _plain(out)


def test_llm_header_names_the_provider_and_says_billed():
    out = render_header(
        {"mode": "synthetic-distractors+llm-eligibility", "llm_provider": "deepseek"}
    )
    plain = _plain(out)
    assert "deepseek" in plain
    assert "billed" in plain, (
        "a billed run must be visibly distinct from the free one — they disagree "
        "by double digits and are otherwise easy to confuse"
    )


def test_header_shortens_the_commit():
    out = render_header({"commit": "708976b2356fba021b3514a58ef52f0beab67abd"})
    assert "708976b" in _plain(out)


# ── headline: the pass line is the verdict ───────────────────────────────

_PASSING = {
    "hygiene_top1_rate": 0.9375,
    "hygiene_pairwise_win_rate": 0.9839,
    "full_top1_rate": 0.9375,
    "semantic_pairwise_win_rate": 0.8571,
    "mean_reference_proxy": 0.8676,
    "mean_reference_oracle": 0.85,
    "candidate_sets": 16,
    "cases_skipped": 0,
    "total_pairs": 69,
}


def test_headline_shows_every_metric():
    out = render_headline(_PASSING)
    plain = _plain(out)
    for label in ("Hygiene top-1", "Full top-1", "Semantic (control)", "Mean oracle reward"):
        assert label in plain
    assert "93.75%" in plain


def test_passing_gate_is_green_and_failing_is_red():
    good = render_headline(dict(_PASSING, hygiene_top1_rate=0.9375))
    bad = render_headline(dict(_PASSING, hygiene_top1_rate=0.8125))
    assert "#10B981" in good  # emerald
    assert "#ef4444" in bad   # red
    assert PASS_LINE == 0.9


def test_semantic_control_is_never_tinted_as_a_failure():
    """It is a CONTROL. No label-free reward can rule out a neighbour span."""
    out = render_headline(dict(_PASSING, semantic_pairwise_win_rate=0.10))
    # The only red in a run whose gating rates pass would have to come from the
    # control row — there should be none.
    assert "#ef4444" not in out


def test_headline_survives_an_empty_summary():
    plain = _plain(render_headline({}))
    assert "n/a" in plain
    assert "0.00%" not in plain


# ── per-distractor breakdown ─────────────────────────────────────────────


def test_by_kind_lists_each_distractor_with_margin_sign():
    out = render_by_kind({
        "page_dump": {"class": "hygiene", "pairs": 14, "reference_wins": 13,
                      "win_rate": 0.9286, "mean_delta": 0.0717},
        "neighbour_span": {"class": "semantic", "pairs": 7, "reference_wins": 6,
                           "win_rate": 0.8571, "mean_delta": 0.0655},
    })
    plain = _plain(out)
    assert "page_dump" in plain and "neighbour_span" in plain
    assert "+0.0717" in plain


def test_by_kind_empty_is_stated_not_blank():
    assert "No distractor breakdown" in _plain(render_by_kind({}))


def test_semantic_row_below_the_line_is_not_flagged_red():
    """Same reasoning as the headline: a control reports a ceiling, not a failure.

    neighbour_span sits at ~85% by construction — it is a correctly quoted but
    wrong provision, and no label-free reward can exclude it. Red would invite
    someone to tune it away, which would mean tuning toward the wrong answer.
    """
    out = render_by_kind({
        "neighbour_span": {"class": "semantic", "pairs": 7, "reference_wins": 6,
                           "win_rate": 0.8571, "mean_delta": 0.0655},
    })
    assert "#ef4444" not in out


def test_hygiene_row_below_the_line_is_flagged_red():
    out = render_by_kind({
        "page_dump": {"class": "hygiene", "pairs": 14, "reference_wins": 11,
                      "win_rate": 0.7857, "mean_delta": 0.0773},
    })
    assert "#ef4444" in out


# ── component discrimination ─────────────────────────────────────────────


def test_components_sort_by_discrimination_descending():
    out = _plain(render_components({
        "eligibility_supported": {"weight": 2.0, "reference_mean": 1.0,
                                  "distractor_mean": 0.899, "discrimination": 0.101},
        "not_truncated": {"weight": 1.5, "reference_mean": 1.0,
                          "distractor_mean": 0.58, "discrimination": 0.42},
    }))
    assert out.index("not_truncated") < out.index("eligibility_supported")


def test_components_carry_the_do_not_reweight_warning():
    out = _plain(render_components({
        "x": {"weight": 1.0, "reference_mean": 1.0, "distractor_mean": 0.5,
              "discrimination": 0.5}
    }))
    assert "reweight" in out, (
        "the discrimination column is partly circular by construction; the "
        "caveat travels with the table or it will be acted on naively"
    )


# ── config ───────────────────────────────────────────────────────────────


def test_config_shows_weights_shares_and_gates():
    out = _plain(render_config({
        "proxy": {
            "component_weights": {"citation_exactness": 3.0, "scope_resolved": 0.5},
            "gates": ["quote_present", "quote_grounded"],
            "quote_dump_gate_chars": 2500,
        }
    }))
    assert "citation_exactness" in out
    assert "quote_present" in out
    assert "quote_dump_gate_chars" in out
    assert "%" in out  # weight share


# ── history ──────────────────────────────────────────────────────────────


def test_history_computes_run_over_run_delta():
    out = _plain(render_history([
        {"generated_at": "2026-07-31T23:10:36", "commit": "708976b" + "0" * 33,
         "hygiene_top1_rate": 0.8125},
        {"generated_at": "2026-08-01T00:40:00", "commit": "c7d2ce9" + "0" * 33,
         "hygiene_top1_rate": 0.9375},
    ]))
    assert "12.50pt" in out
    assert "▲" in out


def test_history_first_run_has_no_delta():
    out = _plain(render_history([
        {"generated_at": "2026-07-31T23:10:36", "hygiene_top1_rate": 0.8125}
    ]))
    assert "pt" not in out


def test_history_empty_is_stated():
    assert "No prior runs" in _plain(render_history([]))


# ── cases ────────────────────────────────────────────────────────────────

_CASE = {
    "case_id": "sgp-cpc-7-5-section-20",
    "country_code": "SGP",
    "indicator_id": "7.5",
    "chunk_index": 3,
    "chunk_chars": 320,
    "hygiene_top1": False,
    "full_top1": False,
    "candidates": [
        {"kind": "reference", "is_reference": True, "quote_chars": 145,
         "quote_preview": "The Public Prosecutor may by written order require",
         "proxy_total": 0.8333, "proxy_gates_passed": True, "proxy_failed_gates": [],
         "oracle_total": 0.85, "evidence_similarity": 1.0,
         "proxy": {"components": {
             "citation_exactness": {"value": 1.0, "weight": 3.0, "detail": "strict substring"},
         }}},
        {"kind": "page_dump", "is_reference": False, "quote_chars": 320,
         "quote_preview": "Section 20. The Public Prosecutor may...",
         "proxy_total": 0.875, "proxy_gates_passed": True, "proxy_failed_gates": [],
         "oracle_total": 0.0, "evidence_similarity": 0.4, "proxy": {"components": {}}},
    ],
    "pairs": [{"kind": "page_dump", "reference_wins": False, "delta": -0.0417}],
}


def test_case_row_matches_the_column_count():
    assert len(case_row(_CASE)) == len(CASE_COLUMNS)


def test_case_row_marks_a_failing_case():
    row = case_row(_CASE)
    assert row[0] == "sgp-cpc-7-5-section-20"
    assert row[3] == "✗"  # hygiene
    assert row[5] == "1"  # one loss


def test_case_row_of_a_clean_case():
    clean = dict(_CASE, hygiene_top1=True, full_top1=True,
                 pairs=[{"kind": "page_dump", "reference_wins": True, "delta": 0.08}])
    row = case_row(clean)
    assert row[3] == "✓" and row[4] == "✓"
    assert row[5] == "–"


def test_render_case_shows_reference_losers_and_candidates():
    out = _plain(render_case(_CASE))
    assert "Reference" in out
    assert "Losers" in out
    assert "page_dump" in out
    assert "-0.0417" in out
    assert "citation_exactness" in out


def test_render_case_reports_no_losses_explicitly():
    clean = dict(_CASE, pairs=[{"kind": "page_dump", "reference_wins": True, "delta": 0.08}])
    assert "outranked every candidate" in _plain(render_case(clean))


def test_render_case_surfaces_failed_gates():
    gated = dict(_CASE)
    gated["candidates"] = [
        dict(_CASE["candidates"][0], proxy_gates_passed=False,
             proxy_failed_gates=["quote_not_a_page_dump"]),
    ]
    assert "quote_not_a_page_dump" in _plain(render_case(gated))


# ── whole-pane composition ───────────────────────────────────────────────


def test_render_summary_and_sections_survive_a_minimal_report():
    """A report missing every optional block must still render, not raise."""
    assert _plain(render_summary({})) is not None
    out = _plain(render_sections({}, []))
    assert "No distractor breakdown" in out
    assert "No prior runs" in out


def test_render_sections_orders_like_the_browser_view():
    report = {
        "by_kind": {"page_dump": {"class": "hygiene", "win_rate": 0.9}},
        "component_analysis": {"not_truncated": {"weight": 1.5, "discrimination": 0.42}},
        "reward_config": {"proxy": {"component_weights": {"citation_exactness": 3.0}},
                          "oracle": {"w_matched": 0.35}},
    }
    out = _plain(render_sections(report, []))
    assert out.index("Per distractor type") < out.index("Component discrimination")
    assert out.index("Component discrimination") < out.index("Proxy reward config")
    assert out.index("Proxy reward config") < out.index("Oracle weights")
    assert out.index("Oracle weights") < out.index("Run history")
