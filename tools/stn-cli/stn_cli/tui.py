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
from textual.theme import Theme
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

# Processors the extract pane can request; blank = backend default
# (RDTII_LLM_PROVIDER). Model per provider follows its env config.
PROVIDERS = ["ollama", "deepseek", "claude", "gemini", "openai", "groq"]

PANES = [
    ("home", "Welcome"),
    ("docs", "Documents"),
    ("discovery", "Discovery"),
    ("extract", "Extract"),
    ("rag", "Chat"),
]

# SENTINEL palette — the app's emerald/teal, not Textual's default accent.
SENTINEL_THEME = Theme(
    name="sentinel",
    primary="#10B981",
    secondary="#0f766e",
    accent="#10B981",
    success="#10B981",
    warning="#f59e0b",
    error="#dc2626",
    foreground="#e7efec",
    background="#0c1210",
    surface="#13201b",
    panel="#182721",
    dark=True,
)


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
    return f"[bold #10B981]\u258d[/][bold {color}] {title}[/]"


def _chip(value: object) -> str:
    if value is True or value == "true":
        return "[#10B981]yes[/]"
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
        preview = str(m.get("chunk_preview") or "")
        if preview:
            out.append("")
            out.append(_h("Chunk preview (raw text)"))
            out.append(f"[dim]{escape(preview)}[/]")
        return "\n".join(out)

    features = m.get("features") or {}
    score = m.get("score", "—")
    out.append(
        f"[bold #10B981]P{m.get('pillar')} · {m.get('indicator')}[/]"
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
        out.append(_h("Flagged for human review", "#f59e0b"))
        for reason in flags or ["(no reason recorded)"]:
            out.append(f"  [#f59e0b]-[/] {escape(str(reason))}")

    quote = str(m.get("verbatim_quote") or "")
    if quote:
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
    badge = "[#10B981]✓ corroborated[/]" if verified else "[#f59e0b]unconfirmed[/]"
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
        border: solid #10B981;
        background: $panel;
        padding: 1 2;
    }
    #report-window Static {
        color: #bec7c3;
    }
    """

    def __init__(self, kind: str, mapping: dict) -> None:
        super().__init__()
        self._kind = kind
        self._mapping = mapping

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="report-window"):
            yield Static(_reasoning_markup(self._kind, self._mapping), id="report-body")

    def on_mount(self) -> None:
        if self._kind != "mapping":
            return
        # Already verified upstream (agent pipeline populates it)? Show inline.
        existing = self._mapping.get("timestamp_verification") or {}
        if existing.get("source_details") or existing.get("verification_log"):
            self._append_verification(_verification_markup(existing))
            return
        # Streaming extractions leave it empty — fetch on demand.
        url = self._mapping.get("source_url")
        if url:
            self._verify(url, self._mapping.get("last_update", ""))

    def _append_verification(self, markup: str) -> None:
        body = self.query_one("#report-body", Static)
        body.update(_reasoning_markup(self._kind, self._mapping) + "\n\n" + markup)

    @work(exclusive=True, group="verify")
    async def _verify(self, url: str, claimed: str) -> None:
        self._append_verification(
            _h("Timestamp verification (forensic)")
            + "\n  [dim]cross-checking Wayback + HTTP Last-Modified…[/]"
        )
        try:
            async with self.app._client(timeout=30.0) as client:
                res = await client.post(
                    "/api/verify/timestamp",
                    json={"url": url, "last_update": claimed},
                )
            if res.status_code == 200:
                self._append_verification(_verification_markup(res.json()))
            else:
                self._append_verification(
                    _h("Timestamp verification (forensic)")
                    + f"\n  [red]HTTP {res.status_code}[/]"
                )
        except httpx.HTTPError as exc:
            self._append_verification(
                _h("Timestamp verification (forensic)")
                + f"\n  [red]unavailable: {exc}[/]"
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

    _FILLED = Style(bgcolor="#10B981")
    _EMPTY = Style(bgcolor="#13201b")

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

    def on_mount(self) -> None:
        self.refresh_body()

    def refresh_body(self) -> None:
        marker = (
            "[bold #10B981]you ›[/]" if self.role == "you" else "[bold cyan]stn ›[/]"
        )
        head = f"{marker} {self._meta}".rstrip()
        self.update(f"{head}\n{escape(self.raw)}" if self.raw else head)

    def set_answer(self, text: str, meta: str = "") -> None:
        self.role = "stn"
        self.raw = text
        self._meta = meta
        self.refresh_body()


class SentinelTUI(App):
    TITLE = "SENTINEL"
    SUB_TITLE = "RDTII AI Mapper"

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
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("1", "pane('docs')", "Documents"),
        ("2", "pane('discovery')", "Discovery"),
        ("3", "pane('extract')", "Extract"),
        ("4", "pane('rag')", "Chat"),
        ("ctrl+r", "run_extract", "Run extract"),
        ("c", "copy_result", "Copy row"),
    ]

    def __init__(self, api: str, token: str) -> None:
        super().__init__()
        self._api = api
        self._token = token
        self._extract_rows: list[tuple[str, dict]] = []
        self._discovery_rows: list[dict] = []
        self._docs_rows: list[str] = []
        self._last_rag_answer: str = ""
        self._rag_msgs: list[tuple[str, str]] = []  # (role, text) for transcript

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
                        f"[bold #10B981]{BANNER}[/]\n"
                        "  SENTINEL — More scientific law observation tool.\n\n"
                        "[#bec7c3] 1 Documents \n 2 Discovery \n 3 Extract \n 4 Chat\n"
                        " \n r refresh \n q quit[/]",
                        id="home-banner",
                    )
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
                    yield Input(
                        placeholder="Ask the knowledge base + Enter", id="rag-input"
                    )
        yield Footer()

    async def on_mount(self) -> None:
        self.register_theme(SENTINEL_THEME)
        self.theme = "sentinel"
        docs = self.query_one("#docs", DataTable)
        docs.add_columns("Filename", "Status", "Country", "Ingested")
        disc = self.query_one("#discovery-table", DataTable)
        disc.add_columns("Title", "Indicators", "URL")
        ext = self.query_one("#extract-table", DataTable)
        ext.add_columns("Indicator", "Score", "Review", "Quote")
        ext.cursor_type = "row"  # row select opens the reasoning report
        await self.query_one("#rag-log", VerticalScroll).mount(
            Static(
                "[dim]Ask something — answers are grounded in the knowledge base."
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
            status.update(
                f"[green]up[/] {data.get('active_provider', '?')} · {self._api}"
            )
        except httpx.HTTPError:
            status.update(f"[red]down[/] · {self._api}")

    @work(exclusive=True, group="load-docs")
    async def _load_docs(self) -> None:
        table = self.query_one("#docs", DataTable)
        table.clear()
        self._docs_rows.clear()
        try:
            async with self._client(timeout=15.0) as client:
                res = await client.get("/api/canvas-files")
            if res.status_code == 401:
                table.add_row("(run `stn login` first)", "", "", "")
                return
            for d in res.json():
                self._docs_rows.append(d.get("filename") or "—")
                table.add_row(
                    (d.get("filename") or "—")[:60],
                    d.get("status", "—"),
                    d.get("country_code") or "—",
                    (d.get("created_at") or "")[:10],
                )
        except httpx.HTTPError as exc:
            table.add_row(f"(error: {exc})", "", "", "")

    # ── actions ──────────────────────────────────────────────────────────

    def action_pane(self, pane_id: str) -> None:
        self.query_one("#switcher", ContentSwitcher).current = pane_id

    async def action_run_extract(self) -> None:
        self.action_pane("extract")
        source = self.query_one("#extract-input", TextArea).text.strip()
        if source:
            self._run_extract(source)

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
            text, label = (self._rag_transcript() or self._last_rag_answer), "conversation"
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
        if event.data_table.id != "extract-table":
            return
        idx = event.cursor_row
        if 0 <= idx < len(self._extract_rows):
            kind, payload = self._extract_rows[idx]
            self.push_screen(ReportScreen(kind, payload))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        if event.input.id == "rag-input":
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

    @work(exclusive=True, group="rag")
    async def _ask_rag(self, question: str) -> None:
        log = self.query_one("#rag-log", VerticalScroll)
        self._rag_msgs.append(("you", question))
        await self._mount_msg(ChatMessage("you", question))
        pending = ChatMessage("stn", "", "[dim]thinking…[/]")
        await self._mount_msg(pending)
        try:
            async with self._client(timeout=300.0) as client:
                res = await client.post(
                    "/api/workflows/nodes/rag.query/run",
                    json={"node_id": "stn-tui", "inputs": {"question": question}},
                )
            outputs = res.json().get("outputs", {})
            retrieved = outputs.get("retrieval_count", 0)
            grounding = (
                f"[dim]({retrieved} chunk(s) retrieved)[/]"
                if retrieved
                else "[yellow]ungrounded[/]"
            )
            answer = outputs.get("answer", "(no answer)")
            self._last_rag_answer = answer
            self._rag_msgs.append(("stn", answer))
            pending.set_answer(answer, grounding)
        except httpx.HTTPError as exc:
            pending.set_answer(f"request failed: {exc}", "[red]error[/]")
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
                            self._extract_rows.append(("mapping", payload))
                            table.add_row(
                                f"P{payload.get('pillar')} · {payload.get('indicator')}",
                                str(payload.get("score", "—")),
                                "[yellow]review[/]"
                                if payload.get("requires_human_review")
                                else "ok",
                                (payload.get("verbatim_quote") or "")[:70],
                            )
                        elif event == "rejected":
                            rejected += 1
                            self._extract_rows.append(("rejected", payload))
                            table.add_row(
                                "[dim]rejected[/]",
                                "[dim]—[/]",
                                "[dim]—[/]",
                                f"[dim]{str(payload.get('reason', ''))[:70]}[/]",
                            )
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
