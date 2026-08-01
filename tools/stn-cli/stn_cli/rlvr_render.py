"""Terminal rendering for the RLVR measurement report — the dataset lab.

Same data, same sections, same reading order as the browser view served at
``/api/rlvr/ui`` (``ai-service/api/rlvr_ui.html``): headline, per-distractor
breakdown, component discrimination, reward config, oracle weights, run
history, and a per-case drill-down. Keeping the two in step matters because
they are two views of ONE artifact — a number that reads 93.75% in the browser
and something else in the terminal would make both untrustworthy.

Everything here is a pure ``dict -> Rich markup`` function so the layout can be
tested without a terminal, an event loop, or a running backend. `tui.py` owns
the widgets, the HTTP, and the key bindings; this module owns what the numbers
look like.

Two conventions carried over from the browser view deliberately:

* **0.9 is the pass line.** `hygiene_top1_rate` is the number that gates wiring
  best-of-N, and the report says below ~90% the reward is not safe to select
  on. Tinting it green/red is not decoration — it is the verdict.
* **Absent is not zero.** A missing metric renders as ``n/a``, never 0.000. The
  offline and --with-llm runs carry different fields, and a blank that looks
  like a real zero is how a stale report gets mistaken for a fresh one.
"""

from __future__ import annotations

from rich.markup import escape

# SENTINEL palette (mirrors tui.py's SENTINEL_THEME / rag_render).
_ACCENT = "#10B981"  # emerald — section bars, headers
_HILITE = "#34d399"  # lighter emerald — emphasised values
_MUTED = "#bec7c3"  # body-dim
_GOOD = "#10B981"
_BAD = "#ef4444"
_WARN = "#f59e0b"

#: The report's own gate: "Below ~90% the reward is not safe to select on."
PASS_LINE = 0.9


def _h(title: str, color: str = "#e7efec") -> str:
    """Section header: accent side-bar + bright title (matches tui.py `_h`)."""
    return f"[bold {_ACCENT}]▍[/][bold {color}] {title}[/]"


def pct(value: object) -> str:
    """Rate as a percentage. ``None`` is n/a, not 0% — they mean different things."""
    try:
        return f"{float(value) * 100:.2f}%"  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "n/a"


def num(value: object, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "n/a"


def signed(value: object, digits: int = 4) -> str:
    """Signed delta — the sign is the point, so it is never dropped."""
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "n/a"
    return f"{f:+.{digits}f}"


def short_commit(commit: object) -> str:
    text = str(commit or "")
    return text[:7] if text else "–"


def _tone(value: object, line: float = PASS_LINE) -> str:
    try:
        return _GOOD if float(value) >= line else _BAD  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return _MUTED


def _delta_markup(value: object, digits: int = 4) -> str:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "[dim]n/a[/]"
    color = _GOOD if f >= 0 else _BAD
    return f"[{color}]{f:+.{digits}f}[/]"


def _bar(rate: object, width: int = 12, control: bool = False) -> str:
    """A tiny meter. Unknown renders as dots, not an empty (i.e. 0%) bar.

    ``control=True`` draws it neutral: a control row is reporting a ceiling, not
    failing a target, and a red bar would invite someone to "fix" it.
    """
    try:
        f = max(0.0, min(1.0, float(rate)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return f"[dim]{'·' * width}[/]"
    filled = int(round(f * width))
    color = _MUTED if control else _tone(f)
    return f"[{color}]{'█' * filled}[/][dim]{'░' * (width - filled)}[/]"


# ── header ────────────────────────────────────────────────────────────────


def render_header(report: dict) -> str:
    """Provenance line: which run is on screen, and did it cost money.

    The mode/provider pair is load-bearing. The offline run and the --with-llm
    run measure different systems and disagree by double digits, so a view that
    shows a rate without saying which produced it is unreadable.
    """
    mode = str(report.get("mode") or "unknown")
    provider = report.get("llm_provider")
    badge = (
        f"[b {_WARN}]{escape(mode)}[/] [dim]· live LLM via[/] "
        f"[b {_WARN}]{escape(str(provider))}[/] [dim]· billed[/]"
        if provider
        else f"[b {_ACCENT}]{escape(mode)}[/] [dim]· offline, free[/]"
    )
    return (
        f"{badge}\n"
        f"[dim]generated[/] {escape(str(report.get('generated_at') or '–'))}   "
        f"[dim]commit[/] {escape(short_commit(report.get('commit')))}   "
        f"[dim]case-set[/] {escape(str(report.get('case_set_sha256') or '–'))[:12]}"
    )


# ── headline ──────────────────────────────────────────────────────────────

#: (label, summary key, sub-caption, is_rate). Order matches the browser view.
HEADLINE_METRICS = [
    ("Hygiene top-1", "hygiene_top1_rate", "proxy picks the real extraction", True),
    ("Hygiene pairwise", "hygiene_pairwise_win_rate", "head-to-head win rate", True),
    ("Full top-1", "full_top1_rate", "incl. wrong-provision control", True),
    ("Semantic (control)", "semantic_pairwise_win_rate", "neighbour-span ceiling", True),
    ("Mean proxy reward", "mean_reference_proxy", "of the real extraction", False),
    ("Mean oracle reward", "mean_reference_oracle", "labelled ceiling 0.85", False),
]

#: Only the gating rates get a pass/fail tint. The semantic row is a CONTROL,
#: not a target — colouring it red would read as a regression to fix, and the
#: report is explicit that no label-free reward can rule out a neighbour span.
_TINTED = {"hygiene_top1_rate", "full_top1_rate"}


def render_headline(summary: dict) -> str:
    lines = [_h("Headline")]
    for label, key, sub, is_rate in HEADLINE_METRICS:
        raw = summary.get(key)
        value = pct(raw) if is_rate else num(raw, 4)
        color = _tone(raw) if key in _TINTED else _HILITE
        lines.append(
            f"  [dim]{escape(label):<20}[/] [b {color}]{value:>8}[/]  [dim]{escape(sub)}[/]"
        )
    sets = summary.get("candidate_sets")
    skipped = summary.get("cases_skipped")
    pairs = summary.get("total_pairs")
    if sets is not None:
        lines.append(
            f"  [dim]{'candidate sets':<20}[/] [b {_MUTED}]{sets:>8}[/]  "
            f"[dim]skipped {skipped} · {pairs} pairs compared[/]"
        )
    return "\n".join(lines)


# ── per distractor type ───────────────────────────────────────────────────


def render_by_kind(by_kind: dict) -> str:
    if not by_kind:
        return _h("Per distractor type") + "\n  [dim]No distractor breakdown in this report.[/]"
    rows = sorted(
        by_kind.items(),
        key=lambda kv: ((kv[1] or {}).get("class") or "", kv[0]),
    )
    lines = [
        _h("Per distractor type"),
        f"  [dim]{'Distractor':<20}{'Class':<10}{'Pairs':>6}{'Wins':>6}  {'Win rate':<22}{'Mean margin':>12}[/]",
    ]
    for kind, entry in rows:
        entry = entry or {}
        rate = entry.get("win_rate")
        # Semantic rows are a CONTROL, not a target — `neighbour_span` is a real,
        # correctly quoted provision that is simply the wrong one, and no
        # label-free reward can rule it out. Tinting it red would read as a
        # regression to chase; it is a ceiling being reported honestly. Same
        # reasoning as _TINTED in the headline.
        is_control = str(entry.get("class") or "") == "semantic"
        rate_markup = (
            f"[dim]{pct(rate):>7}[/]" if is_control else f"[{_tone(rate)}]{pct(rate):>7}[/]"
        )
        lines.append(
            f"  {escape(str(kind)):<20}"
            f"[dim]{escape(str(entry.get('class') or '–')):<10}[/]"
            f"{str(entry.get('pairs', '–')):>6}"
            f"{str(entry.get('reference_wins', '–')):>6}  "
            f"{_bar(rate, control=is_control)} {rate_markup}  "
            f"{_delta_markup(entry.get('mean_delta')):>12}"
        )
    return "\n".join(lines)


# ── component discrimination ──────────────────────────────────────────────


def render_components(analysis: dict) -> str:
    if not analysis:
        return _h("Component discrimination") + "\n  [dim]No component analysis in this report.[/]"
    rows = sorted(
        analysis.items(),
        key=lambda kv: -((kv[1] or {}).get("discrimination") or 0),
    )
    lines = [
        _h("Component discrimination")
        + "  [dim]does each term earn its weight?[/]",
        f"  [dim]{'Component':<26}{'Weight':>7}{'Real':>8}{'Distractor':>12}{'Discrim':>10}[/]",
    ]
    for name, entry in rows:
        entry = entry or {}
        lines.append(
            f"  {escape(str(name)):<26}"
            f"{num(entry.get('weight'), 1):>7}"
            f"{num(entry.get('reference_mean')):>8}"
            f"{num(entry.get('distractor_mean')):>12}"
            f"  {_delta_markup(entry.get('discrimination'), 3):>10}"
        )
    lines.append(
        "  [dim]A component at ~0 carries weight while contributing nothing to the\n"
        "  decision. Do NOT reweight straight off this column — several distractors\n"
        "  were built to break one term, so its score partly measures the distractor.[/]"
    )
    return "\n".join(lines)


# ── reward config ─────────────────────────────────────────────────────────


def render_config(config: dict) -> str:
    proxy = (config or {}).get("proxy") or {}
    weights = proxy.get("component_weights") or {}
    lines = [_h("Proxy reward config")]
    if weights:
        total = sum(weights.values()) or 1
        lines.append(f"  [dim]{'Component':<26}{'Weight':>7}{'Share':>9}[/]")
        for name, weight in sorted(weights.items(), key=lambda kv: -kv[1]):
            lines.append(
                f"  {escape(str(name)):<26}{num(weight, 1):>7}"
                f"[dim]{weight / total * 100:>8.1f}%[/]"
            )
    gates = proxy.get("gates") or []
    if gates:
        lines.append("\n  [dim]Hard gates — any failure collapses the total to 0[/]")
        for gate in gates:
            lines.append(f"    [{_WARN}]•[/] {escape(str(gate))}")
    thresholds = {
        k: v for k, v in proxy.items()
        if k not in {"component_weights", "gates"}
    }
    if thresholds:
        lines.append("\n  [dim]Thresholds[/]")
        for key, value in thresholds.items():
            lines.append(f"    [dim]{escape(str(key)):<34}[/] {escape(str(value))}")
    return "\n".join(lines)


def render_oracle(config: dict) -> str:
    oracle = (config or {}).get("oracle") or {}
    if not oracle:
        return ""
    lines = [
        _h("Oracle weights") + "  [dim]labelled — never seen by the selector[/]"
    ]
    note = oracle.get("score_term_note")
    for key, value in oracle.items():
        if key == "score_term_note":
            continue
        lines.append(f"  [dim]{escape(str(key)):<26}[/] {escape(str(value))}")
    if note:
        lines.append(f"  [dim]{escape(str(note))}[/]")
    return "\n".join(lines)


# ── run history ───────────────────────────────────────────────────────────


def render_history(runs: list[dict]) -> str:
    if not runs:
        return _h("Run history") + "\n  [dim]No prior runs recorded.[/]"
    ordered = sorted(runs, key=lambda r: str(r.get("generated_at") or ""))
    lines = [
        _h("Run history"),
        f"  [dim]{'Generated':<22}{'Commit':<9}{'Hyg top-1':>10}{'Full':>9}"
        f"{'Semantic':>10}{'Mean proxy':>12}{'Δ top-1':>12}[/]",
    ]
    previous = None
    for run in ordered:
        current = run.get("hygiene_top1_rate")
        if previous is None:
            delta = "[dim]–[/]"
        else:
            try:
                diff = float(current) - float(previous)
                arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "=")
                color = _GOOD if diff > 0 else (_BAD if diff < 0 else _MUTED)
                delta = f"[{color}]{arrow} {abs(diff) * 100:.2f}pt[/]"
            except (TypeError, ValueError):
                delta = "[dim]n/a[/]"
        previous = current if current is not None else previous
        lines.append(
            f"  [dim]{escape(str(run.get('generated_at') or '–'))[:21]:<22}[/]"
            f"{escape(short_commit(run.get('commit'))):<9}"
            f"[{_tone(current)}]{pct(current):>10}[/]"
            f"{pct(run.get('full_top1_rate')):>9}"
            f"{pct(run.get('semantic_pairwise_win_rate')):>10}"
            f"{num(run.get('mean_reference_proxy')):>12}"
            f"{delta:>12}"
        )
    return "\n".join(lines)


# ── cases ─────────────────────────────────────────────────────────────────

CASE_COLUMNS = ["Case", "Eco", "Ind", "Hyg", "Full", "Losses", "Proxy"]


def case_row(case: dict) -> tuple[str, str, str, str, str, str, str]:
    """One row of the cases table. Ticks are the at-a-glance verdict."""
    reference = next(
        (c for c in case.get("candidates") or [] if c.get("is_reference")), {}
    )
    losses = [p for p in case.get("pairs") or [] if not p.get("reference_wins")]
    return (
        str(case.get("case_id") or "–"),
        str(case.get("country_code") or "–"),
        str(case.get("indicator_id") or "–"),
        "✓" if case.get("hygiene_top1") else "✗",
        "✓" if case.get("full_top1") else "✗",
        str(len(losses)) if losses else "–",
        num(reference.get("proxy_total")),
    )


def _components_markup(proxy: dict) -> str:
    components = (proxy or {}).get("components") or {}
    if not components:
        return "  [dim]No component breakdown.[/]"
    lines = []
    for name, entry in components.items():
        entry = entry or {}
        lines.append(
            f"  {escape(str(name)):<26} [b {_HILITE}]{num(entry.get('value')):>6}[/]"
            f"  [dim]weight {num(entry.get('weight'), 1)} — "
            f"{escape(str(entry.get('detail') or ''))}[/]"
        )
    return "\n".join(lines)


def render_case(case: dict) -> str:
    """Drill-down for one case — the terminal twin of the browser's <details>."""
    candidates = list(case.get("candidates") or [])
    reference = next((c for c in candidates if c.get("is_reference")), {})
    losses = [p for p in case.get("pairs") or [] if not p.get("reference_wins")]

    head = (
        f"[b {_ACCENT}]{escape(str(case.get('case_id') or '–'))}[/]  "
        f"[dim]{escape(str(case.get('country_code') or '–'))} · "
        f"indicator {escape(str(case.get('indicator_id') or '–'))} · "
        f"chunk {case.get('chunk_index', '–')} · "
        f"{case.get('chunk_chars', '–')} chars[/]\n"
        f"  hygiene {'[%s]✓ pass[/]' % _GOOD if case.get('hygiene_top1') else '[%s]✗ fail[/]' % _BAD}"
        f"   full {'[%s]✓ pass[/]' % _GOOD if case.get('full_top1') else '[%s]✗ fail[/]' % _BAD}"
        f"   [dim]{len(losses)} loss(es)[/]"
    )

    ref_lines = [_h("Reference")]
    for label, key, digits in (
        ("proxy_total", "proxy_total", 4),
        ("oracle_total", "oracle_total", 4),
        ("evidence_similarity", "evidence_similarity", 3),
    ):
        ref_lines.append(
            f"  [dim]{label:<22}[/] {num(reference.get(key), digits)}"
        )
    ref_lines.append(
        f"  [dim]{'oracle_matched':<22}[/] {escape(str(reference.get('oracle_matched', '–')))}"
    )

    if losses:
        loss_lines = [_h("Losers") + "  [dim]beat the reference[/]"]
        for pair in losses:
            loss_lines.append(
                f"  {escape(str(pair.get('kind') or '–')):<22} "
                f"{_delta_markup(pair.get('delta'))}"
            )
    else:
        loss_lines = [
            _h("Losers"),
            "  [dim]None — the reference outranked every candidate.[/]",
        ]

    ordered = sorted(
        candidates,
        key=lambda c: (not c.get("is_reference"), -(c.get("proxy_total") or 0)),
    )
    cand_lines = [
        _h("Candidates"),
        f"  [dim]{'Kind':<20}{'Chars':>7}{'Proxy':>8}{'Oracle':>8}{'EvSim':>7}  Gates[/]",
    ]
    for candidate in ordered:
        kind = "reference" if candidate.get("is_reference") else str(candidate.get("kind") or "–")
        failed = candidate.get("proxy_failed_gates") or []
        gates = (
            f"[{_GOOD}]ok[/]"
            if candidate.get("proxy_gates_passed")
            else f"[{_BAD}]{escape(', '.join(map(str, failed)) or 'failed')}[/]"
        )
        color = _HILITE if candidate.get("is_reference") else _MUTED
        cand_lines.append(
            f"  [{color}]{escape(kind):<20}[/]"
            f"{str(candidate.get('quote_chars', '–')):>7}"
            f"{num(candidate.get('proxy_total'), 4):>8}"
            f"{num(candidate.get('oracle_total'), 3):>8}"
            f"{num(candidate.get('evidence_similarity'), 2):>7}  {gates}"
        )
        preview = str(candidate.get("quote_preview") or "").strip()
        if preview:
            cand_lines.append(f"      [dim]{escape(preview[:150])}[/]")

    return "\n\n".join(
        [
            head,
            "\n".join(ref_lines),
            "\n".join(loss_lines),
            "\n".join(cand_lines),
            _h("Proxy components — reference") + "\n" + _components_markup(reference.get("proxy") or {}),
        ]
    )


# ── whole-report summary (header + headline, for the pane body) ───────────


def render_summary(report: dict) -> str:
    return "\n\n".join(
        [
            render_header(report),
            render_headline(report.get("summary") or {}),
        ]
    )


# ── live runs (trajectory log) ────────────────────────────────────────────
#
# A DIFFERENT artifact from everything above. The golden study measures a frozen
# 16-case set with manufactured distractors and reports top-1 rates; this is what
# the extractor actually produced on real documents. With best-of-N unwired every
# record is a single greedy draw (k=1), so there is no top-1 rate to compute here
# and none is shown — only the distribution of proxy scores over real output, and
# the gate failures, which are the rows worth looking at first.

RUN_COLUMNS = ["Run", "Provider", "Recs", "Docs", "Mean proxy", "Gate fails"]
CANDIDATE_COLUMNS = ["Indicator", "Proxy", "Gates", "Chunk", "Quote"]


def run_row(entry: dict) -> tuple[str, str, str, str, str, str]:
    failures = entry.get("gate_failures") or 0
    return (
        str(entry.get("run_id") or "–")[:24],
        str(entry.get("provider") or "–")[:14],
        str(entry.get("records", "–")),
        str(entry.get("documents", "–")),
        num(entry.get("mean_proxy"), 4),
        str(failures) if failures else "–",
    )


def candidate_row(record: dict) -> tuple[str, str, str, str, str]:
    proxy = record.get("proxy") or {}
    quote = str((record.get("candidate") or {}).get("verbatim_quote") or "")
    return (
        str(record.get("indicator_id") or "–"),
        num(proxy.get("total"), 4),
        "ok" if proxy.get("passed_gates") else "FAIL",
        str(record.get("chunk_index", "–")),
        " ".join(quote.split())[:70],
    )


def render_live_summary(payload: dict) -> str:
    """Header + distribution for the live extraction log."""
    runs = payload.get("runs") or []
    records = payload.get("records") or []
    total = payload.get("total", 0)
    totals = [
        (r.get("proxy") or {}).get("total")
        for r in records
        if isinstance((r.get("proxy") or {}).get("total"), (int, float))
    ]
    gate_fails = sum(
        1 for r in records if (r.get("proxy") or {}).get("passed_gates") is False
    )
    lines = [
        f"[b {_ACCENT}]live extraction candidates[/] [dim]· k=1 greedy · not the golden study[/]",
        f"[dim]{total} record(s) across {len(runs)} run(s)[/]   "
        f"[dim]{escape(str(payload.get('path') or ''))}[/]",
        "",
        _h("Distribution"),
    ]
    if totals:
        ordered = sorted(totals)
        mid = len(ordered) // 2
        median = (
            ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
        )
        lines += [
            f"  [dim]{'mean proxy':<20}[/] [b {_HILITE}]{sum(totals) / len(totals):>8.4f}[/]",
            f"  [dim]{'median':<20}[/] [b {_HILITE}]{median:>8.4f}[/]",
            f"  [dim]{'min / max':<20}[/] [b {_HILITE}]{min(totals):>8.4f}[/] [dim]/[/] "
            f"[b {_HILITE}]{max(totals):.4f}[/]",
        ]
    else:
        lines.append("  [dim]no scored candidates yet[/]")
    tone = _BAD if gate_fails else _GOOD
    lines.append(
        f"  [dim]{'gate failures':<20}[/] [b {tone}]{gate_fails:>8}[/]  "
        "[dim]reward collapses to 0 — returned but unusable as evidence[/]"
    )
    return "\n".join(lines)


def render_runs(payload: dict) -> str:
    runs = payload.get("runs") or []
    if not runs:
        return _h("Runs") + "\n  [dim]No extraction runs logged yet.[/]"
    lines = [
        _h("Runs") + "  [dim]newest first[/]",
        f"  [dim]{'Run':<26}{'Provider':<16}{'Recs':>6}{'Docs':>6}{'Mean proxy':>12}{'Gate fails':>12}[/]",
    ]
    for entry in runs:
        failures = entry.get("gate_failures") or 0
        lines.append(
            f"  {escape(str(entry.get('run_id') or '–'))[:25]:<26}"
            f"[dim]{escape(str(entry.get('provider') or '–'))[:15]:<16}[/]"
            f"{str(entry.get('records', '–')):>6}"
            f"{str(entry.get('documents', '–')):>6}"
            f"{num(entry.get('mean_proxy'), 4):>12}"
            + (f"[{_BAD}]{failures:>12}[/]" if failures else f"[dim]{'–':>12}[/]")
        )
        indicators = entry.get("indicators") or []
        if indicators:
            lines.append(f"      [dim]{escape(', '.join(map(str, indicators)))}[/]")
    return "\n".join(lines)


def render_candidate(record: dict) -> str:
    """Drill-down for one logged candidate."""
    candidate = record.get("candidate") or {}
    proxy = record.get("proxy") or {}
    failed = proxy.get("failed_gates") or []
    head = (
        f"[b {_ACCENT}]{escape(str(record.get('indicator_id') or '–'))}[/]  "
        f"[dim]{escape(str(record.get('provider') or '–'))} · "
        f"{escape(str(record.get('model') or '–'))} · "
        f"doc {escape(str(record.get('document_id') or '–'))} · "
        f"chunk {record.get('chunk_index', '–')}[/]\n"
        f"  [dim]logged[/] {escape(str(record.get('logged_at') or '–'))}\n"
        f"  [dim]run[/] {escape(str(record.get('run_id') or '–'))}\n"
        f"  [dim]quote_hash[/] {escape(str(record.get('quote_hash') or '–'))}"
        "  [dim](join key to a human verdict)[/]"
    )
    gates = (
        f"[{_GOOD}]all gates passed[/]"
        if proxy.get("passed_gates")
        else f"[{_BAD}]failed: {escape(', '.join(map(str, failed)) or 'unknown')}[/]"
    )
    score = (
        f"{_h('Proxy reward')}\n"
        f"  [b {_HILITE}]{num(proxy.get('total'), 6)}[/]   {gates}"
    )
    quote = str(candidate.get("verbatim_quote") or "")
    evidence = [
        _h("Candidate"),
        f"  [dim]{'article_clause':<22}[/] {escape(str(candidate.get('article_clause') or '–'))}",
        f"  [dim]{'source_legislation':<22}[/] {escape(str(candidate.get('source_legislation') or '–'))}",
        f"  [dim]{'scope':<22}[/] {escape(str(candidate.get('scope') or '–'))}",
        f"  [dim]{'source_url':<22}[/] {escape(str(candidate.get('source_url') or '–'))}",
        "",
        f"  [dim]{escape(quote[:600])}[/]",
    ]
    return "\n\n".join(
        [
            head,
            score,
            "\n".join(evidence),
            _h("Proxy components") + "\n" + _components_markup(proxy),
        ]
    )


def render_sections(report: dict, history: list[dict] | None = None) -> str:
    """Everything below the fold, in the browser view's order."""
    parts = [
        render_by_kind(report.get("by_kind") or {}),
        render_components(report.get("component_analysis") or {}),
        render_config(report.get("reward_config") or {}),
    ]
    oracle = render_oracle(report.get("reward_config") or {})
    if oracle:
        parts.append(oracle)
    parts.append(render_history(history or []))
    return "\n\n".join(parts)
