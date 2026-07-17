"""SENTINEL TUI — spotify-tui-style dashboard over the backend API.

Launched via `stn tui`. Sidebar (1-4) switches panes:
  1 Documents — knowledge-base table (r to refresh)
  2 Discovery — type "SGP data localisation" and hit Enter
  3 Extract   — URL or pasted legal text -> indicator mappings (classic Source->Audit)
  4 RAG chat  — ask the knowledge base, answers land in the log
"""

from __future__ import annotations

import json

import httpx
from textual import events, work
from textual.app import App, ComposeResult
from textual.message import Message
from textual.theme import Theme
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    ContentSwitcher,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    ProgressBar,
    RichLog,
    Select,
    TextArea,
)

# Processors the extract pane can request; blank = backend default
# (RDTII_LLM_PROVIDER). Model per provider follows its env config.
PROVIDERS = ["ollama", "deepseek", "claude", "gemini", "openai", "groq"]

PANES = [
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
        margin: 1 2;
        display: none;
    }
    #extract-bar.running {
        display: block;
    }
    RichLog {
        border: none;
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
    ]

    def __init__(self, api: str, token: str) -> None:
        super().__init__()
        self._api = api
        self._token = token

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
            with ContentSwitcher(initial="docs", id="switcher"):
                yield DataTable(id="docs")
                with Vertical(id="discovery"):
                    yield DataTable(id="discovery-table")
                    yield Input(
                        placeholder="ISO3-or-name [keywords] + Enter, e.g. SGP data localisation",
                        id="discovery-input",
                    )
                with Vertical(id="extract"):
                    yield Label(
                        "Paste a URL or legal text below · Enter extracts · Shift+Enter newline",
                        id="extract-status",
                    )
                    with Horizontal(id="extract-controls"):
                        yield Select(
                            [(p, p) for p in PROVIDERS],
                            prompt="processor: backend default",
                            id="extract-provider",
                        )
                        yield ProgressBar(
                            id="extract-bar", show_eta=False
                        )
                    yield DataTable(id="extract-table")
                    yield ExtractInput(id="extract-input")
                with Vertical(id="rag"):
                    yield RichLog(id="rag-log", wrap=True, markup=True)
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
        self.query_one("#rag-log", RichLog).write(
            "[dim]Ask something — answers are grounded in the knowledge base.[/]"
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
        try:
            async with self._client(timeout=15.0) as client:
                res = await client.get("/api/canvas-files")
            if res.status_code == 401:
                table.add_row("(run `stn login` first)", "", "", "")
                return
            for d in res.json():
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

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        pane_id = (event.item.id or "").removeprefix("nav-")
        if pane_id:
            self.action_pane(pane_id)

    async def on_extract_input_submitted(self, event: ExtractInput.Submitted) -> None:
        await self.action_run_extract()

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

    @work(exclusive=True, group="rag")
    async def _ask_rag(self, question: str) -> None:
        log = self.query_one("#rag-log", RichLog)
        log.write(f"\n[bold green]you >[/] {question}")
        log.write("[dim]thinking…[/]")
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
            log.write(f"[bold cyan]stn >[/] {grounding}")
            log.write(outputs.get("answer", "(no answer)"))
        except httpx.HTTPError as exc:
            log.write(f"[red]request failed: {exc}[/]")

    @work(exclusive=True, group="extract")
    async def _run_extract(self, source: str) -> None:
        """Stream the extraction: each mapping's quote lands as it's found."""
        status = self.query_one("#extract-status", Label)
        table = self.query_one("#extract-table", DataTable)
        table.clear()
        is_url = source.startswith(("http://", "https://"))
        form = {"source_url": source} if is_url else {"text": source}
        chosen = self.query_one("#extract-provider", Select).value
        if isinstance(chosen, str):  # unselected is a Select.NULL sentinel
            form["provider"] = chosen
        status.update(
            f"starting extraction stream via {form.get('provider', 'backend default')}…"
        )
        # Indeterminate pulse until the first progress event — covers the
        # silent crawl/PDF-parse phase of URL extractions.
        bar = self.query_one("#extract-bar", ProgressBar)
        bar.add_class("running")
        bar.update(total=None)
        mapped = rejected = 0
        provider = "?"
        try:
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
                                bar.update(
                                    total=total,
                                    progress=max(0, (payload.get("current") or 1) - 1),
                                )
                            status.update(
                                f"extracting chunk {payload.get('current')}/{payload.get('total')} "
                                f"· candidates: {', '.join(payload.get('indicators', []))} "
                                f"· {mapped} mapped, {rejected} rejected"
                            )
                        elif event == "mapping":
                            mapped += 1
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
            if res.status_code != 200:
                table.add_row(f"HTTP {res.status_code}: {res.text[:80]}", "", "")
                return
            for c in res.json().get("candidates", []):
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
