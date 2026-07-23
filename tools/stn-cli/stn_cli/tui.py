"""SENTINEL TUI — spotify-tui-style dashboard over the backend API.

Launched via `stn tui`. Sidebar (1-4) switches panes:
  1 Documents — knowledge-base table (r to refresh)
  2 Discovery — type "SGP data localisation" and hit Enter
  3 Extract   — URL or pasted legal text -> indicator mappings (classic Source->Audit)
  4 RAG chat  — ask the knowledge base, answers land in the log
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from rich.markup import escape
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.strip import Strip
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import (
    ContentSwitcher,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    Static,
    TextArea,
)

from .main import BANNER
from .rag_render import render_answer
from .theme import load_config, rebind_bindings

# Processors the extract pane can request; blank = backend default
# (RDTII_LLM_PROVIDER). Model per provider follows its env config.
PROVIDERS = ["deepseek", "ollama", "claude", "gemini", "openai", "groq"]

PANES = [
    ("home", "Welcome"),
    ("docs", "Documents"),
    ("discovery", "Discovery"),
    ("extract", "Extract"),
    ("rag", "Chat"),
]

# SENTINEL palette — the app's emerald/teal by default, user-overridable via
# ~/.config/stn/theme.toml (see stn_cli.theme for resolution + precedence).
THEME_CONFIG = load_config()
SENTINEL_THEME = THEME_CONFIG.to_theme()
# Inline-markup shorthands for the spots Textual CSS variables can't reach.
# .rich() strips any alpha byte — Rich markup/Style can't parse 8-digit hex.
_P = THEME_CONFIG.rich("primary")
_WARN = THEME_CONFIG.rich("warning")


# Same key groupings as the browser's ReasoningReport.tsx — doc/OCR quality
# and provenance metadata are context, everything else is a scoring input.
DOC_QUALITY_KEYS = {
    "mean_confidence",
    "ocr_ratio",
    "pdf_type",
    "total_pages",
    "ocr_pages",
    "text_pages",
    "_ocr_mean_confidence",
    "_ocr_ratio",
    "_pdf_type",
}
PROVENANCE_KEYS = {
    "source_file_sha256",
    "source_pdf_path",
    "_source_grade",
    "_source_grade_confidence",
    "_timeframe_status",
    "_timeframe_column",
}


def _h(title: str, color: str = "#e7efec") -> str:
    """Section subtitle: accent side-bar + bright title, set off from body."""
    return f"[bold {_P}]\u258d[/][bold {color}] {title}[/]"


def _chip(value: object) -> str:
    if value is True or value == "true":
        return f"[{_P}]yes[/]"
    if value is False or value == "false":
        return "[red]no[/]"
    return escape(str(value))


def _percent(value: object) -> str | None:
    try:
        return f"{round(float(value) * 100)}%"
    except (TypeError, ValueError):
        return None


def _reasoning_markup(kind: str, m: dict) -> str:
    """TUI edition of the browser Reasoning Report for one table row."""
    out: list[str] = []
    if kind == "rejected":
        out.append(_h("Rejected extraction", "#dc2626"))
        out.append("")
        out.append(f"[bold]Reason[/]  {escape(str(m.get('reason', '—')))}")
        if m.get("candidate_indicator"):
            supported = ", ".join(m.get("supported_indicators") or []) or "NONE"
            out.append(
                f"[bold]Candidate[/]  {escape(str(m['candidate_indicator']))}"
                f"  · decision {escape(str(m.get('decision', 'insufficient')))}"
                f"  · verifier supported {escape(supported)}"
            )
        for reason in m.get("exclusion_reasons") or []:
            out.append(f"  [{_WARN}]-[/] {escape(str(reason))}")
        preview = str(m.get("chunk_preview") or "")
        if preview:
            out.append("")
            out.append(_h("Chunk preview (raw text)"))
            out.append(f"[dim]{escape(preview)}[/]")
        return "\n".join(out)

    features = m.get("features") or {}
    score = m.get("score", "—")
    out.append(
        f"[bold {_P}]P{m.get('pillar')} · {m.get('indicator')}[/]"
        f"  score [bold]{score}[/]  · scope {escape(str(m.get('scope', '—')))}"
        f" · via {escape(str(m.get('extraction_provider', '—')))}"
    )
    if m.get("source_legislation") or m.get("source_url"):
        out.append(
            f"[dim]{escape(str(m.get('source_legislation') or ''))}"
            f"  {escape(str(m.get('source_url') or ''))}[/]"
        )

    flags = m.get("flag_reasons") or []
    if m.get("requires_human_review"):
        out.append("")
        out.append(_h("Flagged for human review", _WARN))
        for reason in flags or ["(no reason recorded)"]:
            out.append(f"  [{_WARN}]-[/] {escape(str(reason))}")

    quote = str(m.get("verbatim_quote") or "")
    context = str(m.get("quote_context") or "")
    if context and quote and context.strip() != quote.strip():
        # Display-only completion: show the whole sentence, with the model's
        # actual quote in bold and the recovered context dimmed. Scoring still
        # uses the model's clip (verbatim_quote).
        out.append("")
        out.append(_h("Provision (model quote in bold)"))
        idx = context.find(quote)
        if idx >= 0:
            before, after = context[:idx], context[idx + len(quote) :]
            out.append(
                f"  [dim]{escape(before)}[/][bold]{escape(quote)}[/]"
                f"[dim]{escape(after)}[/]"
            )
        else:
            out.append("  " + escape(context))
    elif quote:
        out.append("")
        out.append(_h("Verbatim quote (raw text)"))
        out.append("  " + escape(quote))

    if m.get("impact"):
        out.append("")
        out.append(_h("Score justification"))
        out.append("  " + escape(str(m["impact"])))

    scoring = {
        k: v
        for k, v in features.items()
        if k not in DOC_QUALITY_KEYS and k not in PROVENANCE_KEYS
    }
    if scoring:
        out.append("")
        out.append(_h("Scoring inputs (static check rules)"))
        pad = max(len(k.lstrip("_")) for k in scoring)
        for k, v in scoring.items():
            label = k.lstrip("_").replace("_", " ")
            out.append(f"  {escape(label.ljust(pad))}  {_chip(v)}")

    stats: list[str] = []
    pdf_type = features.get("_pdf_type", features.get("pdf_type"))
    if pdf_type is not None:
        stats.append(f"document type {escape(str(pdf_type))}")
    if features.get("total_pages") is not None:
        pages = features["total_pages"]
        ocr_pages = features.get("ocr_pages")
        stats.append(
            f"OCR coverage {ocr_pages}/{pages} pp"
            if ocr_pages is not None
            else f"{pages} pp"
        )
    conf = _percent(
        features.get("_ocr_mean_confidence", features.get("mean_confidence"))
    )
    if conf:
        stats.append(f"OCR confidence {conf}")
    if stats:
        out.append("")
        out.append(_h("Document quality"))
        out.append("  " + " · ".join(stats))

    prov: list[str] = []
    grade = features.get("_source_grade")
    if grade is not None:
        grade_conf = _percent(features.get("_source_grade_confidence"))
        prov.append(
            f"source grade  {escape(str(grade))}"
            + (f" · {grade_conf} confidence" if grade_conf else "")
        )
    tf_col = features.get("_timeframe_column")
    tf_status = features.get("_timeframe_status")
    if tf_col or tf_status:
        prov.append(
            "timeframe  "
            + " ".join(
                filter(
                    None,
                    [str(tf_col or "")] + ([f"({tf_status})"] if tf_status else []),
                )
            )
        )
    if features.get("source_file_sha256"):
        prov.append(f"sha-256  {escape(str(features['source_file_sha256']))}")
    if features.get("source_pdf_path"):
        prov.append(f"file  {escape(str(features['source_pdf_path']))}")
    if prov:
        out.append("")
        out.append(_h("Provenance"))
        for line in prov:
            out.append(f"  [dim]{line}[/]")
    return "\n".join(out)


def _row_plaintext(kind: str, m: dict) -> str:
    """Clipboard-ready plain text of a result row (markup stripped)."""
    return Text.from_markup(_reasoning_markup(kind, m)).plain


def _verification_markup(data: dict) -> str:
    """Forensic timestamp-verification block (crawler.verify_law_timeline)."""
    out = [_h("Timestamp verification (forensic)")]
    verified = data.get("verified")
    badge = f"[{_P}]✓ corroborated[/]" if verified else f"[{_WARN}]unconfirmed[/]"
    best = data.get("best_date") or "—"
    out.append(
        f"  {badge}  best date [bold]{escape(str(best))}[/]"
        f"  · {data.get('sources_checked', 0)} source(s) checked"
    )
    for sd in data.get("source_details", []):
        out.append(
            f"  [dim]{escape(str(sd.get('source', '')))}: "
            f"{escape(str(sd.get('date') or '—'))} "
            f"({escape(str(sd.get('status', '')))})[/]"
        )
    log = data.get("verification_log")
    if log:
        out.append(f"  [dim]{escape(str(log))}[/]")
    return "\n".join(out)


_YEAR_TITLE = "Release year (4 signals · weighted · LLM-decided)"


def _release_year_markup(data: dict) -> str:
    """Weighted release-year resolution block (crawler-free)."""
    out = [_h(_YEAR_TITLE)]
    year = data.get("year")
    if not year:
        out.append("  [dim]no year signal found (no title/manifest/timeframe hit)[/]")
        return "\n".join(out)
    conf = data.get("confidence") or 0.0
    out.append(
        f"  [bold {_P}]{year}[/]  · {round(conf * 100)}% weighted support"
        f"  · decided by {escape(str(data.get('decided_by', '')))}"
    )
    cands = data.get("candidates") or {}
    if cands:
        parts = ", ".join(f"{escape(str(m))} {y}" for m, y in cands.items())
        out.append(f"  [dim]signals: {parts}[/]")
    return "\n".join(out)


class ReportScreen(ModalScreen):
    """Inner window: reasoning report for a selected extract row."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
        ("c", "copy_report", "Copy"),
    ]

    CSS = """
    ReportScreen {
        align: center middle;
    }
    #report-window {
        width: 84%;
        height: 80%;
        border: solid $primary;
        background: $panel;
        padding: 1 2;
    }
    #report-window Static {
        color: #bec7c3;
    }
    """

    _EXTRA_ORDER = ["year", "timestamp"]

    def __init__(self, kind: str, mapping: dict) -> None:
        super().__init__()
        self._kind = kind
        self._mapping = mapping
        self._extras: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="report-window"):
            yield Static(_reasoning_markup(self._kind, self._mapping), id="report-body")

    def on_mount(self) -> None:
        if self._kind != "mapping":
            return
        # Release year — resolvable from the citation, no URL needed.
        self._resolve_year()
        # Forensic timestamp — inline if the agent pipeline populated it, else
        # fetch when there's a source URL to archive-check.
        existing = self._mapping.get("timestamp_verification") or {}
        if existing.get("source_details") or existing.get("verification_log"):
            self._set_extra("timestamp", _verification_markup(existing))
        elif self._mapping.get("source_url"):
            self._verify(
                self._mapping["source_url"], self._mapping.get("last_update", "")
            )

    def _set_extra(self, key: str, markup: str) -> None:
        self._extras[key] = markup
        ordered = [self._extras[k] for k in self._EXTRA_ORDER if k in self._extras]
        self.query_one("#report-body", Static).update(
            "\n\n".join([_reasoning_markup(self._kind, self._mapping), *ordered])
        )

    @work(exclusive=True, group="year")
    async def _resolve_year(self) -> None:
        m = self._mapping
        feats = m.get("features") or {}
        self._set_extra("year", _h(_YEAR_TITLE) + "\n  [dim]resolving…[/]")
        try:
            async with self.app._client(timeout=90.0) as client:
                res = await client.post(
                    "/api/verify/release-year",
                    json={
                        "source_legislation": m.get("source_legislation", ""),
                        "quote": m.get("verbatim_quote", ""),
                        "last_update": m.get("last_update", ""),
                        "timeframe_column": str(feats.get("_timeframe_column", "")),
                    },
                )
            if res.status_code == 200:
                self._set_extra("year", _release_year_markup(res.json()))
            else:
                self._set_extra(
                    "year", _h(_YEAR_TITLE) + f"\n  [red]HTTP {res.status_code}[/]"
                )
        except httpx.HTTPError as exc:
            self._set_extra("year", _h(_YEAR_TITLE) + f"\n  [red]unavailable: {exc}[/]")

    @work(exclusive=True, group="verify")
    async def _verify(self, url: str, claimed: str) -> None:
        self._set_extra(
            "timestamp",
            _h("Timestamp verification (forensic)")
            + "\n  [dim]cross-checking Wayback + HTTP Last-Modified…[/]",
        )
        try:
            async with self.app._client(timeout=30.0) as client:
                res = await client.post(
                    "/api/verify/timestamp",
                    json={"url": url, "last_update": claimed},
                )
            if res.status_code == 200:
                self._set_extra("timestamp", _verification_markup(res.json()))
            else:
                self._set_extra(
                    "timestamp",
                    _h("Timestamp verification (forensic)")
                    + f"\n  [red]HTTP {res.status_code}[/]",
                )
        except httpx.HTTPError as exc:
            self._set_extra(
                "timestamp",
                _h("Timestamp verification (forensic)")
                + f"\n  [red]unavailable: {exc}[/]",
            )

    def action_copy_report(self) -> None:
        selection = self.get_selected_text()
        if selection:
            self.app._copy(selection)
            self.app.notify("Copied selection to clipboard", timeout=2)
            return
        self.app._copy(_row_plaintext(self._kind, self._mapping))
        self.app.notify("Report copied to clipboard", timeout=2)


class BlockBar(Widget):
    """Solid full-height progress block (ProgressBar's Bar is 1 line tall).

    percentage None = indeterminate: a block marches across the width.
    """

    percentage: reactive[float | None] = reactive(None)

    _FILLED = Style(bgcolor=THEME_CONFIG.rich("primary"))
    _EMPTY = Style(bgcolor=THEME_CONFIG.rich("surface"))

    def on_mount(self) -> None:
        self._march = 0
        self.set_interval(0.12, self._tick)

    def _tick(self) -> None:
        if self.percentage is None and self.styles.display != "none":
            self._march += 2
            self.refresh()

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        if width <= 0:
            return Strip.blank(width)
        if self.percentage is None:
            block = max(4, width // 5)
            start = self._march % (width + block) - block
            left = min(max(start, 0), width)
            right = min(max(start + block, 0), width)
            segments = [
                Segment(" " * left, self._EMPTY),
                Segment(" " * (right - left), self._FILLED),
                Segment(" " * (width - right), self._EMPTY),
            ]
        else:
            filled = round(width * min(1.0, max(0.0, self.percentage)))
            segments = [
                Segment(" " * filled, self._FILLED),
                Segment(" " * (width - filled), self._EMPTY),
            ]
        return Strip(segments, width)


def _resolve_local_file(raw: str) -> Path | None:
    """Interpret the input as a dragged-in local file path, if it is one.

    Dragging a file onto the terminal pastes its path — possibly as a
    file:// URI, quoted, or with backslash-escaped spaces — not the file.
    """
    candidate = raw.strip()
    if not candidate or "\n" in candidate:
        return None
    if candidate.startswith("file://"):
        candidate = unquote(urlparse(candidate).path)
    if len(candidate) > 1 and candidate[0] == candidate[-1] and candidate[0] in "'\"":
        candidate = candidate[1:-1]
    candidate = re.sub(r"\\(.)", r"\1", candidate)
    path = Path(candidate).expanduser()
    try:
        return path if path.is_file() else None
    except OSError:
        return None


class ExtractInput(TextArea):
    """TextArea where Enter submits and Shift+Enter inserts a newline.

    Enter must be intercepted here — the focused TextArea eats it for a
    newline before any app-level binding can see it. Ctrl+J also inserts
    a newline, for terminals that can't tell Shift+Enter from Enter.
    """

    class Submitted(Message):
        pass

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(self.Submitted())
            return
        if event.key in ("shift+enter", "ctrl+j"):
            event.stop()
            event.prevent_default()
            self.insert("\n")
            return
        await super()._on_key(event)


# Thinking animation: braille spinner + RAG-pipeline phase verbs. The phase
# advances every ~3s and holds on the last — long waits read as "drafting",
# not a stuck spinner.
_SPINNER_FRAMES = THEME_CONFIG.spinner
_THINK_PHASES = THEME_CONFIG.phases
_THINK_PHASE_SECS = THEME_CONFIG.phase_secs


def thinking_meta(frame: int, elapsed: float, verb: str | None = None) -> str:
    """Markup for one animation tick (pure — the timer just feeds it)."""
    spin = _SPINNER_FRAMES[frame % len(_SPINNER_FRAMES)]
    if verb is None:
        verb = _THINK_PHASES[
            min(int(elapsed // _THINK_PHASE_SECS), len(_THINK_PHASES) - 1)
        ]
    tail = f" · {elapsed:.0f}s" if elapsed >= _THINK_PHASE_SECS else ""
    return f"[dim]{spin} {verb}…{tail}[/]"


class ChatMessage(Static):
    """One chat turn, as its own selectable block.

    A Static (unlike RichLog) so its text is mouse-selectable; users select
    and copy with the terminal's own selection/copy.
    """

    def __init__(self, role: str, text: str, meta: str = "") -> None:
        super().__init__()
        self.role = role
        self.raw = text
        self._meta = meta
        self._think_timer = None
        self._think_verb: str | None = None
        self._think_frame = 0
        self._think_start = 0.0

    def on_mount(self) -> None:
        if THEME_CONFIG.chat_message_opacity < 1.0:
            self.styles.opacity = THEME_CONFIG.chat_message_opacity
        self.refresh_body()

    def start_thinking(self, verb: str | None = None) -> None:
        """Animate the pending state until set_answer() lands.

        verb pins the label (e.g. "ingesting foo.pdf"); None cycles the
        RAG-pipeline phases.
        """
        self.stop_thinking()
        self._think_verb = verb
        self._think_frame = 0
        self._think_start = time.monotonic()
        self._think_timer = self.set_interval(0.1, self._tick_thinking)
        self._tick_thinking()

    def stop_thinking(self) -> None:
        if self._think_timer is not None:
            self._think_timer.stop()
            self._think_timer = None

    def _tick_thinking(self) -> None:
        self._think_frame += 1
        elapsed = time.monotonic() - self._think_start
        self._meta = thinking_meta(self._think_frame, elapsed, self._think_verb)
        self.refresh_body()

    def refresh_body(self) -> None:
        marker = (
            f"[bold {THEME_CONFIG.you_marker or _P}]you ›[/]"
            if self.role == "you"
            else f"[bold {THEME_CONFIG.stn_marker}]stn ›[/]"
        )
        head = f"{marker} {self._meta}".rstrip()
        if not self.raw:
            self.update(head)
            return
        # The user's own question is shown verbatim; the assistant's answer is
        # web-oriented Markdown, so render it to themed terminal markup.
        body = render_answer(self.raw) if self.role == "stn" else escape(self.raw)
        self.update(f"{head}\n{body}")

    def set_answer(self, text: str, meta: str = "") -> None:
        self.stop_thinking()
        self.role = "stn"
        self.raw = text
        self._meta = meta
        self.refresh_body()


# Extract result table: (header label, sort key) per column, in display order.
EXTRACT_COLS = [
    ("Indicator", "indicator"),
    ("Score", "score"),
    ("Review", "review"),
    ("Quote", "quote"),
    ("Year", "year"),
]

_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")


def _title_year_int(p: dict) -> int | None:
    """Earliest plausible year in the legislation citation (fast, no LLM).

    The title-year is the release-year resolver's strongest signal; the full
    4-signal, LLM-decided resolution still lives in the row's report.
    """
    for src in (p.get("source_legislation"), p.get("verbatim_quote")):
        years = [int(y) for y in _YEAR_RE.findall(str(src or ""))]
        if years:
            return min(years)
    return None


def _extract_row_cells(kind: str, p: dict) -> tuple[str, str, str, str, str]:
    """The 5 display cells for one extract result row."""
    if kind == "rejected":
        return (
            "[dim]rejected[/]",
            "[dim]—[/]",
            "[dim]—[/]",
            f"[dim]{str(p.get('reason', ''))[:70]}[/]",
            "[dim]—[/]",
        )
    year = _title_year_int(p)
    return (
        f"P{p.get('pillar')} · {p.get('indicator')}",
        str(p.get("score", "—")),
        "[yellow]review[/]" if p.get("requires_human_review") else "ok",
        (p.get("verbatim_quote") or "")[:70],
        str(year) if year else "[dim]—[/]",
    )


def _extract_sort_key(col: str):
    """Sort key over a (kind, payload) row for the given column."""

    def key(row: tuple[str, dict]):
        _kind, p = row
        if col == "indicator":
            return tuple(
                int(n) for n in re.findall(r"\d+", str(p.get("indicator") or ""))
            )
        if col == "score":
            try:
                return (float(p.get("score")),)
            except (TypeError, ValueError):
                return (-1.0,)
        if col == "review":
            return (0 if p.get("requires_human_review") else 1,)
        if col == "quote":
            return ((p.get("verbatim_quote") or "").lower(),)
        if col == "year":
            return (_title_year_int(p) or 0,)
        return ()

    return key


class SentinelTUI(App):
    TITLE = "SENTINEL"
    SUB_TITLE = "RDTII AI Mapper"

    # Single source of truth for the chat prompt — compose and _set_scope both
    # use this so the placeholder never says two different things.
    RAG_PLACEHOLDER = "Ask the KB · or paste a file path to ingest · + Enter"
    # transparent=true keeps the terminal's own (possibly translucent)
    # background: ansi_color stops Textual converting ANSI-default to a
    # concrete color, and the theme's background is ansi_default.
    ansi_color = THEME_CONFIG.transparent

    CSS = """
    #sidebar {
        width: 26;
        border-right: solid $accent;
    }
    #sidebar ListItem {
        padding: 0 1;
    }
    #status {
        color: $text-muted;
        padding: 0 1;
    }
    #switcher {
        padding: 0 1;
    }
    Input {
        dock: bottom;
    }
    #extract-input {
        dock: bottom;
        height: 6;
        border: solid $secondary;
    }
    #extract-controls {
        height: 3;
    }
    #extract-provider {
        width: 34;
    }
    #extract-bar {
        width: 1fr;
        height: 1fr;
        margin: 0 0 0 2;
        display: none;
    }
    #extract-bar.running {
        display: block;
    }
    #rag-log {
        height: 1fr;
    }
    ChatMessage {
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    #home {
        align: center middle;
    }
    #home-banner {
        width: auto;
        content-align: center top;
    }
    #home-stats {
        width: auto;
        height: auto;
        margin: 1 0;
    }
    #home-stats Static {
        width: 18;
        height: 4;
        margin: 0 1;
        padding: 0 1;
        border: round $primary 40%;
        content-align: left top;
    }
    #home-keys {
        width: auto;
        color: $text-muted;
        content-align: center top;
    }
    Screen {
        layers: base leader;
    }
    #leader-popup {
        layer: leader;
        dock: bottom;
        width: 100%;
        height: auto;
        max-height: 12;
        padding: 0 2;
        background: $panel;
        border-top: solid $primary;
    }
    """

    DEFAULT_BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("1", "pane('docs')", "Documents"),
        ("2", "pane('discovery')", "Discovery"),
        ("3", "pane('extract')", "Extract"),
        ("4", "pane('rag')", "Chat"),
        ("ctrl+r", "run_extract", "Run extract"),
        ("c", "copy_result", "Copy row"),
        ("s", "sort_extract", "Sort"),
        ("u", "sync_doc", "Save to DB"),
    ]
    BINDINGS = rebind_bindings(DEFAULT_BINDINGS, THEME_CONFIG.key_direct)
    # action -> human label, for the which-key popup rows.
    ACTION_LABELS = {action: label for _, action, label in DEFAULT_BINDINGS}

    def __init__(self, api: str, token: str) -> None:
        super().__init__()
        self._api = api
        self._token = token
        self._leader_pending = False
        self._leader_timer = None
        self._extract_rows: list[tuple[str, dict]] = []
        self._extract_col_keys: list = []
        self._sort_col: str | None = None
        self._sort_reverse: bool = False
        self._discovery_rows: list[dict] = []
        self._docs_rows: list[str] = []
        self._docs: list[dict] = []  # full doc dicts, parallel to _docs_rows
        self._last_rag_answer: str = ""
        self._rag_msgs: list[tuple[str, str]] = []  # (role, text) for transcript
        # Chat scope: when set, retrieval is restricted to this one document
        # (fixes cross-country contamination — an unscoped query dredges the
        # whole store and unrelated economies out-rank the answer).
        self._scope_doc_id: str | None = None
        self._scope_label: str = ""

    # ── welcome dashboard ────────────────────────────────────────────────

    @staticmethod
    def _stat_tile(label: str, value: str) -> str:
        return f"[dim]{escape(label)}[/]\n[bold {_P}]{escape(value)}[/]"

    def _set_stat(self, tile_id: str, value: str) -> None:
        try:
            self.query_one(f"#{tile_id}", Static).update(
                self._stat_tile(self._STAT_LABELS[tile_id], value)
            )
        except Exception:  # noqa: BLE001 — home not mounted / pane switched
            pass

    _STAT_LABELS = {
        "stat-backend": "Backend",
        "stat-provider": "Provider",
        "stat-docs": "Documents",
        "stat-emb": "Embeddings",
    }

    def _home_keys_markup(self) -> str:
        """Live keybinding hints — reflects rebinds AND the leader map, so the
        welcome screen never lies about which key does what."""
        lead = THEME_CONFIG.leader
        if lead and THEME_CONFIG.key_map:
            pretty = lead.upper() if len(lead) > 1 else lead
            pairs = [
                f"[bold {_P}]{pretty} {key}[/] {escape(self.ACTION_LABELS.get(act, act))}"
                for key, act in sorted(THEME_CONFIG.key_map.items())
            ]
        else:
            # No leader configured → show the direct bindings actually in force.
            pairs = [
                f"[bold {_P}]{escape(key)}[/] {escape(label)}"
                for key, _act, label in self.BINDINGS
                if not key.startswith("ctrl")
            ]
        return "   ".join(pairs)

    # ── layout ───────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield ListView(
                    *[
                        ListItem(Label(label), id=f"nav-{pane_id}")
                        for pane_id, label in PANES
                    ]
                )
                yield Label("", id="status")
            with ContentSwitcher(initial="home", id="switcher"):
                with Vertical(id="home"):
                    yield Static(
                        f"[bold {_P}]{BANNER}[/]\n  Aimed for RDTII 2.1.",
                        id="home-banner",
                    )
                    with Horizontal(id="home-stats"):
                        yield Static(self._stat_tile("Backend", "…"), id="stat-backend")
                        yield Static(self._stat_tile("Provider", "…"), id="stat-provider")
                        yield Static(self._stat_tile("Documents", "…"), id="stat-docs")
                        yield Static(self._stat_tile("Embeddings", "…"), id="stat-emb")
                    yield Static(self._home_keys_markup(), id="home-keys")
                yield DataTable(id="docs")
                with Vertical(id="discovery"):
                    yield DataTable(id="discovery-table")
                    yield Input(
                        placeholder="ISO3-or-name [keywords] + Enter, e.g. SGP data localisation",
                        id="discovery-input",
                    )
                with Vertical(id="extract"):
                    yield Label(
                        "Paste a URL, legal text, or drag a file below · Enter extracts · Shift+Enter newline",
                        id="extract-status",
                    )
                    with Horizontal(id="extract-controls"):
                        yield Select(
                            [(p, p) for p in PROVIDERS],
                            value=PROVIDERS[0],
                            allow_blank=False,
                            id="extract-provider",
                        )
                        yield BlockBar(id="extract-bar")
                    yield DataTable(id="extract-table")
                    yield ExtractInput(id="extract-input")
                with Vertical(id="rag"):
                    yield VerticalScroll(id="rag-log")
                    yield Input(placeholder=self.RAG_PLACEHOLDER, id="rag-input")
        yield Footer()

    async def on_mount(self) -> None:
        self.register_theme(SENTINEL_THEME)
        self.theme = "sentinel"
        docs = self.query_one("#docs", DataTable)
        docs.add_columns("Filename", "Status", "Emb", "Country", "Ingested")
        disc = self.query_one("#discovery-table", DataTable)
        disc.add_columns("Title", "Indicators", "URL")
        ext = self.query_one("#extract-table", DataTable)
        self._extract_col_keys = list(ext.add_columns(*[c[0] for c in EXTRACT_COLS]))
        ext.cursor_type = "row"  # row select opens the reasoning report
        await self.query_one("#rag-log", VerticalScroll).mount(
            Static(
                "[dim]Select a document to scope the chat · /all clears scope"
                "  ·  select text with the mouse to copy.[/]",
                id="rag-hint",
            )
        )
        self.query_one("#status", Label).update("[dim]connecting…[/]")
        self._load_status()
        self._load_docs()

    # ── http ─────────────────────────────────────────────────────────────

    def _client(self, timeout: float = 60.0) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        return httpx.AsyncClient(base_url=self._api, timeout=timeout, headers=headers)

    @work(exclusive=True, group="load-status")
    async def _load_status(self) -> None:
        status = self.query_one("#status", Label)
        try:
            async with self._client(timeout=5.0) as client:
                data = (await client.get("/health")).json()
            provider = data.get("active_provider", "?")
            status.update(f"[green]up[/] {provider} · {self._api}")
            self._set_stat("stat-backend", "up")
            self._set_stat("stat-provider", provider)
        except httpx.HTTPError:
            status.update(f"[red]down[/] · {self._api}")
            self._set_stat("stat-backend", "down")

    @work(exclusive=True, group="load-docs")
    async def _load_docs(self) -> None:
        table = self.query_one("#docs", DataTable)
        table.clear()
        self._docs_rows.clear()
        self._docs.clear()
        try:
            async with self._client(timeout=15.0) as client:
                res = await client.get("/api/canvas-files")
            if res.status_code == 401:
                table.add_row("(run `stn login` first)", "", "", "", "")
                return
            total_emb = 0
            for d in res.json():
                self._docs_rows.append(d.get("filename") or "—")
                self._docs.append(d)
                emb = d.get("embeddings")
                total_emb += emb if isinstance(emb, int) else 0
                status = d.get("status", "—")
                # A 'processed' row with 0 embeddings is a phantom — say so
                # rather than let it read as a healthy document.
                if emb == 0 and status == "processed":
                    status = "empty"
                table.add_row(
                    (d.get("filename") or "—")[:60],
                    status,
                    "—" if emb is None else str(emb),
                    d.get("country_code") or "—",
                    (d.get("created_at") or "")[:10],
                )
            self._set_stat("stat-docs", str(len(self._docs)))
            self._set_stat("stat-emb", f"{total_emb:,}")
        except httpx.HTTPError as exc:
            table.add_row(f"(error: {exc})", "", "", "")

    # ── actions ──────────────────────────────────────────────────────────

    # ── leader key (LazyVim-style) ───────────────────────────────────────
    # <leader> then a mapped key runs an action. While pending: a floating
    # which-key popup lists the choices vertically, and flash.nvim-style
    # jump labels light up the sidebar panes that have a mapped key. Never
    # fires while an Input/TextArea is focused ("insert mode"), so a space
    # leader still types spaces in the chat box.

    _PANE_ACTION = re.compile(r"^pane\('(\w+)'\)$")

    def _leader_popup_markup(self) -> str:
        rows = [f"[bold]{THEME_CONFIG.leader.upper()}[/] ›"]
        for key, action in sorted(THEME_CONFIG.key_map.items()):
            label = self.ACTION_LABELS.get(action, action)
            rows.append(f" [bold {_P}]{key}[/]  {escape(label)}")
        return "\n".join(rows)

    def _flash_pane_labels(self, on: bool) -> None:
        """flash.nvim-style jump labels on the sidebar while leader pends."""
        keys_by_pane = {
            m.group(1): key
            for key, action in THEME_CONFIG.key_map.items()
            if (m := self._PANE_ACTION.match(action))
        }
        for pane_id, label in PANES:
            key = keys_by_pane.get(pane_id)
            if not key:
                continue
            try:
                widget = self.query_one(f"#nav-{pane_id} Label", Label)
            except Exception:  # noqa: BLE001 — sidebar not mounted yet
                continue
            widget.update(
                f"[reverse bold {_P}] {key} [/] {label}" if on else label
            )

    async def _enter_leader(self) -> None:
        self._leader_pending = True
        self._leader_timer = self.set_timer(
            THEME_CONFIG.leader_timeout, self._clear_leader
        )
        await self.mount(Static(self._leader_popup_markup(), id="leader-popup"))
        self._flash_pane_labels(True)

    def _clear_leader(self) -> None:
        self._leader_pending = False
        if self._leader_timer is not None:
            self._leader_timer.stop()
            self._leader_timer = None
        self._flash_pane_labels(False)
        try:
            self.query_one("#leader-popup", Static).remove()
        except Exception:  # noqa: BLE001 — popup already gone
            pass

    async def on_key(self, event: events.Key) -> None:
        if not THEME_CONFIG.leader:
            return
        if isinstance(self.focused, (Input, TextArea)):
            return  # insert mode — leader never fires, keys type normally
        if self._leader_pending:
            event.stop()
            event.prevent_default()
            action = THEME_CONFIG.key_map.get(event.key)
            self._clear_leader()
            if action:
                await self.run_action(action)
            return
        if event.key == THEME_CONFIG.leader:
            event.stop()
            event.prevent_default()
            await self._enter_leader()

    def action_pane(self, pane_id: str) -> None:
        self.query_one("#switcher", ContentSwitcher).current = pane_id

    async def action_run_extract(self) -> None:
        self.action_pane("extract")
        source = self.query_one("#extract-input", TextArea).text.strip()
        if source:
            self._run_extract(source)

    def action_sync_doc(self) -> None:
        """Push the selected document through _save_to_db and update its status.

        The 'button' for the Documents pane: completes a document stuck in
        'processing' (or re-embeds one) via the sync ingest endpoint.
        """
        if self.query_one("#switcher", ContentSwitcher).current != "docs":
            return
        idx = self.query_one("#docs", DataTable).cursor_row
        if not (0 <= idx < len(self._docs)):
            self.notify("Select a document row first", severity="warning", timeout=2)
            return
        doc = self._docs[idx]
        doc_id = doc.get("document_id")
        if not doc_id:
            self.notify("Row has no document id", severity="warning", timeout=2)
            return
        self._sync_doc(idx, str(doc_id), doc.get("filename") or "?")

    @work(exclusive=False, group="sync-doc")
    async def _sync_doc(self, row: int, doc_id: str, filename: str) -> None:
        table = self.query_one("#docs", DataTable)

        def set_status(text: str) -> None:
            # Column 1 is Status (Filename, Status, Country, Ingested).
            try:
                table.update_cell_at((row, 1), text)
            except Exception:  # noqa: BLE001 — table may have refreshed
                pass

        set_status("saving…")
        try:
            async with self._client(timeout=600.0) as client:
                res = await client.post(f"/api/canvas-files/{doc_id}/process")
            if res.status_code != 200:
                try:
                    detail = res.json().get("detail", res.text[:80])
                except ValueError:
                    detail = res.text[:80]
                set_status("failed")
                self.notify(f"{filename}: {detail}", severity="error", timeout=4)
                return
            data = res.json()
            chunks = data.get("chunks")
            set_status(data.get("status", "processed"))
            self.notify(
                f"{filename} → {data.get('status', 'processed')}"
                + (f" · {chunks} chunk(s)" if chunks is not None else ""),
                timeout=3,
            )
            self._load_docs()  # re-pull so counts/status are authoritative
        except httpx.HTTPError as exc:
            set_status("failed")
            self.notify(f"{filename}: {exc}", severity="error", timeout=4)

    async def action_refresh(self) -> None:
        self._load_status()
        self._load_docs()

    def _copy(self, text: str) -> None:
        """Copy to clipboard via OSC 52 AND the local OS tool.

        OSC 52 covers most terminals + SSH but is silently ignored by some
        (e.g. macOS Terminal.app); the OS command (pbcopy/wl-copy/xclip)
        covers local use where OSC 52 fails. Belt and suspenders.
        """
        self.copy_to_clipboard(text)  # OSC 52
        import shutil
        import subprocess

        for cmd in (
            ["pbcopy"],
            ["wl-copy"],
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ):
            if shutil.which(cmd[0]):
                try:
                    subprocess.run(cmd, input=text.encode(), timeout=2, check=False)
                except (OSError, subprocess.SubprocessError):
                    pass
                break

    def action_copy_result(self) -> None:
        """Copy to the clipboard: a live text selection if any, else the row.

        Mouse-dragged text selection wins (chat blocks, Static, inputs); otherwise
        fall back to the current result row (tables can't text-select).
        """
        selection = self.screen.get_selected_text()
        if selection:
            self._copy(selection)
            self.notify("Copied selection to clipboard", timeout=2)
            return
        pane = self.query_one("#switcher", ContentSwitcher).current
        text, label = None, "result"
        if pane == "extract":
            idx = self.query_one("#extract-table", DataTable).cursor_row
            if 0 <= idx < len(self._extract_rows):
                kind, payload = self._extract_rows[idx]
                text, label = _row_plaintext(kind, payload), "mapping report"
        elif pane == "discovery":
            idx = self.query_one("#discovery-table", DataTable).cursor_row
            if 0 <= idx < len(self._discovery_rows):
                text = (self._discovery_rows[idx].get("url") or "").strip()
                label = "source URL"
        elif pane == "docs":
            idx = self.query_one("#docs", DataTable).cursor_row
            if 0 <= idx < len(self._docs_rows):
                text, label = self._docs_rows[idx], "filename"
        elif pane == "rag":
            text, label = (
                (self._rag_transcript() or self._last_rag_answer),
                "conversation",
            )
        if text:
            self._copy(text)
            self.notify(f"Copied {label} to clipboard", timeout=2)
        else:
            self.notify("Nothing to copy here", severity="warning", timeout=2)

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        pane_id = (event.item.id or "").removeprefix("nav-")
        if pane_id:
            self.action_pane(pane_id)

    async def on_extract_input_submitted(self, event: ExtractInput.Submitted) -> None:
        await self.action_run_extract()

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "extract-table":
            idx = event.cursor_row
            if 0 <= idx < len(self._extract_rows):
                kind, payload = self._extract_rows[idx]
                self.push_screen(ReportScreen(kind, payload))
            return
        if event.data_table.id == "docs":
            # Selecting a document scopes the chat to it.
            idx = event.cursor_row
            if 0 <= idx < len(self._docs):
                self._set_scope(self._docs[idx])

    # ── extract sorting (click a column title, or press `s` to cycle) ────

    def _add_extract_row(self, kind: str, payload: dict) -> None:
        """Append a streamed result, keeping any active sort applied."""
        self._extract_rows.append((kind, payload))
        if self._sort_col:
            self._apply_extract_sort()  # rows arrive out of order → re-sort
        else:
            self.query_one("#extract-table", DataTable).add_row(
                *_extract_row_cells(kind, payload)
            )

    def _apply_extract_sort(self) -> None:
        mappings = [r for r in self._extract_rows if r[0] == "mapping"]
        rejected = [r for r in self._extract_rows if r[0] == "rejected"]
        if self._sort_col:
            mappings.sort(
                key=_extract_sort_key(self._sort_col), reverse=self._sort_reverse
            )
        self._extract_rows = mappings + rejected  # rejected always last
        table = self.query_one("#extract-table", DataTable)
        table.clear()
        for kind, payload in self._extract_rows:
            table.add_row(*_extract_row_cells(kind, payload))
        # arrow on the sorted header (+ a status line, in case the terminal
        # doesn't re-render the header label).
        for (label, col), key in zip(EXTRACT_COLS, self._extract_col_keys):
            arrow = (
                (" ▼" if self._sort_reverse else " ▲") if self._sort_col == col else ""
            )
            try:
                table.columns[key].label = Text(label + arrow)
            except Exception:  # noqa: BLE001
                pass
        table.refresh()

    def _set_extract_sort(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_reverse = not self._sort_reverse  # re-select toggles direction
        else:
            self._sort_col, self._sort_reverse = col, False
        self._apply_extract_sort()
        self.query_one("#extract-status", Label).update(
            f"sorted by [bold]{col}[/] {'▼ desc' if self._sort_reverse else '▲ asc'}"
        )

    def action_sort_extract(self) -> None:
        """Keyboard: cycle the sort to the next column (ascending)."""
        cols = [c[1] for c in EXTRACT_COLS]
        i = cols.index(self._sort_col) if self._sort_col in cols else -1
        self._set_extract_sort(cols[(i + 1) % len(cols)])

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        if event.data_table.id != "extract-table":
            return
        try:
            idx = list(self._extract_col_keys).index(event.column_key)
        except ValueError:
            return
        self._set_extract_sort(EXTRACT_COLS[idx][1])

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        if event.input.id == "rag-input":
            if text == "/all":
                self._set_scope(None)
            elif (local := _resolve_local_file(text)) is not None:
                # A dragged-in / pasted file path → ingest it (fire straight to
                # _save_to_db) and scope the chat to it, rather than treat the
                # path as a question.
                self._ingest_local_file(local)
            else:
                self._ask_rag(text)
        elif event.input.id == "discovery-input":
            self._run_discovery(text)

    # ── features ─────────────────────────────────────────────────────────

    def _rag_transcript(self) -> str:
        """The whole conversation as plain text (for 'copy conversation')."""
        return "\n\n".join(f"{role} > {text}" for role, text in self._rag_msgs)

    async def _mount_msg(self, message: ChatMessage) -> None:
        log = self.query_one("#rag-log", VerticalScroll)
        await log.mount(message)
        log.scroll_end(animate=False)

    def _set_scope(self, doc: dict | None) -> None:
        """Restrict (or clear) the document the chat retrieves from."""
        if doc and doc.get("document_id"):
            self._scope_doc_id = str(doc["document_id"])
            fn = (doc.get("filename") or "?")[:40]
            cc = doc.get("country_code") or "—"
            self._scope_label = f"{fn} · {cc}"
            self.notify(f"Chat scoped to {self._scope_label}", timeout=3)
        else:
            self._scope_doc_id = None
            self._scope_label = ""
            self.notify("Chat scope cleared — searching the whole store", timeout=3)
        try:
            self.query_one("#rag-input", Input).placeholder = (
                f"[scope: {self._scope_label}] ask + Enter · /all clears"
                if self._scope_doc_id
                else self.RAG_PLACEHOLDER
            )
        except Exception:  # noqa: BLE001 — placeholder is cosmetic
            pass

    @work(exclusive=True, group="rag")
    async def _ingest_local_file(self, local: Path) -> None:
        """Upload a local file and fire it straight through _save_to_db, then
        scope the chat to the freshly ingested document."""
        note = ChatMessage("stn", "", f"[dim]ingesting {escape(local.name)}…[/]")
        await self._mount_msg(note)
        note.start_thinking(f"ingesting {escape(local.name)}")
        mime = "application/pdf" if local.suffix.lower() == ".pdf" else "text/plain"
        try:
            async with self._client(timeout=600.0) as client:
                res = await client.post(
                    "/api/canvas-files",
                    params={"sync": "true"},  # fire directly to _save_to_db
                    files={"file": (local.name, local.read_bytes(), mime)},
                )
            if res.status_code != 200:
                try:
                    detail = res.json().get("detail", res.text[:120])
                except ValueError:
                    detail = res.text[:120]
                note.set_answer("", f"[red]ingest failed: {escape(str(detail))}[/]")
                return
            data = res.json()
            chunks = data.get("chunks")
            summary = f"{local.name} → {data.get('status', '?')}"
            if chunks is not None:
                summary += f", {chunks} chunk(s)"
            if data.get("deduplicated"):
                summary += " (already ingested)"
            note.set_answer(summary, "[green]ingested[/]")
            self._load_docs()  # refresh the Documents table
            self._set_scope(
                {"document_id": data.get("document_id"), "filename": local.name}
            )
        except (OSError, httpx.HTTPError) as exc:
            note.set_answer("", f"[red]ingest failed: {escape(str(exc))}[/]")
        finally:
            note.stop_thinking()  # same orphaned-spinner guard as _ask_rag
        self.query_one("#rag-log", VerticalScroll).scroll_end(animate=False)

    @work(exclusive=True, group="rag")
    async def _ask_rag(self, question: str) -> None:
        log = self.query_one("#rag-log", VerticalScroll)
        self._rag_msgs.append(("you", question))
        await self._mount_msg(ChatMessage("you", question))
        pending = ChatMessage("stn", "", "[dim]thinking…[/]")
        await self._mount_msg(pending)
        pending.start_thinking()
        inputs: dict = {"question": question}
        if self._scope_doc_id:
            # Session-scoped retrieval — the whole point of this path.
            inputs["document_ids"] = [self._scope_doc_id]
        try:
            async with self._client(timeout=300.0) as client:
                res = await client.post(
                    "/api/workflows/nodes/rag.query/run",
                    json={"node_id": "stn-tui", "inputs": inputs},
                )
            outputs = res.json().get("outputs", {})
            retrieved = outputs.get("retrieval_count", 0)
            scope = " · scoped" if self._scope_doc_id else ""
            grounding = (
                f"[dim]({retrieved} chunk(s){scope})[/]"
                if retrieved
                else "[yellow]ungrounded[/]"
            )
            answer = outputs.get("answer", "(no answer)")
            self._last_rag_answer = answer
            self._rag_msgs.append(("stn", answer))
            pending.set_answer(answer, grounding)
        except httpx.HTTPError as exc:
            pending.set_answer(f"request failed: {exc}", "[red]error[/]")
        finally:
            # Exclusive worker: a newer question cancels this one — freeze the
            # orphaned spinner so it can't claim to still be working.
            pending.stop_thinking()
        log.scroll_end(animate=False)

    async def _parse_local_file(self, local: Path, status: Label) -> str | None:
        """Turn a dragged-in file into extractable text; None on failure.

        PDFs go through the backend's /api/parse-file (same parser the web
        canvas Run flow uses); plain-text files are read directly.
        """
        suffix = local.suffix.lower()
        try:
            if suffix == ".pdf":
                status.update(f"parsing {local.name} on backend…")
                async with self._client(timeout=300.0) as client:
                    res = await client.post(
                        "/api/parse-file",
                        files={
                            "file": (local.name, local.read_bytes(), "application/pdf")
                        },
                    )
                if res.status_code != 200:
                    detail = res.json().get("detail", res.text[:100])
                    status.update(f"[red]parse failed: {detail}[/]")
                    return None
                return res.json().get("text", "")
            if suffix in (".txt", ".md", ""):
                return local.read_text(errors="replace")
            status.update(f"[red]unsupported file type: {suffix}[/] (pdf/txt/md)")
            return None
        except (OSError, httpx.HTTPError) as exc:
            status.update(f"[red]could not read {local.name}: {exc}[/]")
            return None

    @work(exclusive=True, group="extract")
    async def _run_extract(self, source: str) -> None:
        """Stream the extraction: each mapping's quote lands as it's found."""
        status = self.query_one("#extract-status", Label)
        table = self.query_one("#extract-table", DataTable)
        table.clear()
        self._extract_rows.clear()
        form: dict[str, str] = {}
        chosen = self.query_one("#extract-provider", Select).value
        if isinstance(chosen, str):  # unselected is a Select.NULL sentinel
            form["provider"] = chosen
        # Indeterminate pulse until the first progress event — covers the
        # silent crawl/parse phase of URL and file extractions.
        bar = self.query_one("#extract-bar", BlockBar)
        bar.add_class("running")
        bar.percentage = None
        mapped = rejected = 0
        provider = "?"
        try:
            local = _resolve_local_file(source)
            if local is not None:
                text = await self._parse_local_file(local, status)
                if text is None:
                    return
                form["text"] = text
            elif source.startswith(("http://", "https://")):
                form["source_url"] = source
            else:
                form["text"] = source
            status.update(
                f"starting extraction stream via "
                f"{form.get('provider', 'backend default')}…"
            )
            async with self._client(timeout=600.0) as client:
                async with client.stream(
                    "POST", "/api/extract/stream", data=form
                ) as res:
                    if res.status_code != 200:
                        body = (await res.aread()).decode()[:120]
                        status.update(f"[red]HTTP {res.status_code}[/] {body}")
                        return
                    event = ""
                    async for line in res.aiter_lines():
                        if line.startswith("event: "):
                            event = line[7:].strip()
                            continue
                        if not line.startswith("data: "):
                            continue
                        try:
                            payload = json.loads(line[6:])
                        except ValueError:
                            continue
                        if event == "progress":
                            total = payload.get("total") or 0
                            if total:
                                done = max(0, (payload.get("current") or 1) - 1)
                                bar.percentage = done / total
                            status.update(
                                f"extracting chunk {payload.get('current')}/{payload.get('total')} "
                                f"· candidates: {', '.join(payload.get('indicators', []))} "
                                f"· {mapped} mapped, {rejected} rejected"
                            )
                        elif event == "mapping":
                            mapped += 1
                            self._add_extract_row("mapping", payload)
                        elif event == "rejected":
                            rejected += 1
                            self._add_extract_row("rejected", payload)
                        elif event == "error":
                            status.update(f"[red]{str(payload.get('detail'))[:100]}[/]")
                            return
                        elif event == "done":
                            provider = payload.get("provider", provider)
        except httpx.HTTPError as exc:
            status.update(f"[red]stream failed: {exc}[/]")
            return
        finally:
            bar.remove_class("running")
        status.update(
            f"[bold]{mapped}[/] mapping(s) · {rejected} rejected · via {provider}"
        )

    @work(exclusive=True, group="discovery")
    async def _run_discovery(self, text: str) -> None:
        parts = text.split(maxsplit=1)
        country, keywords = parts[0], parts[1] if len(parts) > 1 else ""
        table = self.query_one("#discovery-table", DataTable)
        table.clear()
        table.add_row("searching…", "", "")
        try:
            async with self._client(timeout=180.0) as client:
                res = await client.post(
                    "/api/discovery/search",
                    json={
                        "country_code": country.upper(),
                        "keywords": keywords,
                        "limit": 10,
                    },
                )
            table.clear()
            self._discovery_rows.clear()
            if res.status_code != 200:
                table.add_row(f"HTTP {res.status_code}: {res.text[:80]}", "", "")
                return
            for c in res.json().get("candidates", []):
                self._discovery_rows.append(c)
                table.add_row(
                    (c.get("title") or "—")[:60],
                    ",".join(c.get("matched_indicators", [])),
                    (c.get("url") or "")[:70],
                )
        except httpx.HTTPError as exc:
            table.clear()
            table.add_row(f"error: {exc}", "", "")


def run_tui(api: str, token: str) -> None:
    SentinelTUI(api=api, token=token).run()
