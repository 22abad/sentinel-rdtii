"""SENTINEL CLI — operate the RDTII AI Mapper from the terminal.

Talks to the running FastAPI backend (default http://localhost:8000, override
with STN_API). Start the stack with `make dev` first.

    stn status
    stn discovery AUS --keywords "data localisation" --limit 5
    stn rag "What does the PDPA say about cross-border transfer?"
    stn docs
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

BANNER = r"""
   _____ _______   _____________   __________
  / ___// ____/ | / /_  __/  _/ | / / ____/ /
  \__ \/ __/ /  |/ / / /  / //  |/ / __/ / /
 ___/ / /___/ /|  / / / _/ // /|  / /___/ /___
/____/_____/_/ |_/ /_/ /___/_/ |_/_____/_____/
"""

app = typer.Typer(
    name="stn",
    # The \b paragraph marker tells the help formatter to keep the ASCII
    # art's line breaks instead of reflowing it to terminal width.
    help="\b"
    + BANNER
    + "\n\nSENTINEL — operate discovery, RAG, and the knowledge base.",
    no_args_is_help=True,
)
console = Console()

API = os.getenv("STN_API", "http://localhost:8000").rstrip("/")

CREDENTIALS_PATH = Path.home() / ".config" / "stn" / "credentials.json"


def _load_credentials() -> dict:
    try:
        return json.loads(CREDENTIALS_PATH.read_text())
    except (OSError, ValueError):
        return {}


def _save_credentials(data: dict) -> None:
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_PATH.write_text(json.dumps(data, indent=2))
    CREDENTIALS_PATH.chmod(0o600)  # bearer credential — owner-only


def _auth_token() -> str:
    # Explicit env wins (CI/scripts); otherwise the stored login.
    return os.getenv("STN_TOKEN", "") or _load_credentials().get("access_token", "")


def _client(timeout: float = 120.0) -> httpx.Client:
    headers = {}
    token = _auth_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=API, timeout=timeout, headers=headers)


def _jwt_claims(token: str) -> dict:
    # Display-only payload decode — NO signature verification.
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:  # noqa: BLE001 — malformed token is just "unknown"
        return {}


def _die(message: str) -> None:
    console.print(f"[bold red]✗[/] {message}")
    raise typer.Exit(code=1)


@app.command()
def login(email: str = typer.Option(..., prompt=True, help="Account email")) -> None:
    """Log in and save your token."""
    password = typer.prompt("Password", hide_input=True)
    try:
        with _client(timeout=15.0) as client:
            res = client.post(
                "/auth/login", json={"email": email, "password": password}
            )
    except httpx.HTTPError as exc:
        _die(f"Backend unreachable at {API} — is `make dev` running? ({exc})")
        return
    if res.status_code != 200:
        detail = (
            res.json().get("detail", res.status_code) if res.text else res.status_code
        )
        _die(f"Login failed: {detail}")
        return
    data = res.json()
    _save_credentials(
        {
            "access_token": data["access_token"],
            "username": data.get("username", ""),
            "email": data.get("email", email),
            "api": API,
        }
    )
    console.print(
        f"[bold green]✓[/] Logged in as [bold]{data.get('username', email)}[/] — token stored."
    )


@app.command()
def logout() -> None:
    """Log out."""
    if CREDENTIALS_PATH.exists():
        CREDENTIALS_PATH.unlink()
        console.print("[green]✓[/] Logged out — stored token removed.")
    else:
        console.print("[dim]No stored login.[/]")


@app.command()
def whoami() -> None:
    """Show who is logged in."""
    token = _auth_token()
    if not token:
        _die("Not logged in — run `stn login` (or export STN_TOKEN).")
        return
    creds = _load_credentials()
    claims = _jwt_claims(token)
    exp = claims.get("exp")
    expires = (
        datetime.fromtimestamp(exp, tz=timezone.utc)
        .astimezone()
        .strftime("%Y-%m-%d %H:%M")
        if isinstance(exp, (int, float))
        else "unknown"
    )
    expired = (
        isinstance(exp, (int, float))
        and datetime.now(tz=timezone.utc).timestamp() > exp
    )
    table = Table(show_header=False, box=None)
    table.add_row(
        "[bold]User[/]", claims.get("username") or creds.get("username") or "—"
    )
    table.add_row("[bold]Email[/]", creds.get("email", "—"))
    table.add_row(
        "[bold]Token expires[/]", f"[red]{expires} (expired)[/]" if expired else expires
    )
    table.add_row(
        "[bold]Source[/]",
        "STN_TOKEN env" if os.getenv("STN_TOKEN") else str(CREDENTIALS_PATH),
    )
    console.print(
        Panel(table, title="stn whoami", border_style="red" if expired else "cyan")
    )


@app.command()
def status() -> None:
    """Backend health and providers."""
    try:
        with _client(timeout=5.0) as client:
            data = client.get("/health").json()
    except httpx.HTTPError as exc:
        _die(f"Backend unreachable at {API} — is `make dev` running? ({exc})")
        return
    table = Table(show_header=False, box=None)
    table.add_row("[bold]Backend[/]", f"[green]up[/] · {API}")
    table.add_row("[bold]Active provider[/]", str(data.get("active_provider", "—")))
    table.add_row(
        "[bold]Available[/]", ", ".join(data.get("available_providers", []) or ["—"])
    )
    console.print(Panel(table, title="stn status", border_style="green"))


@app.command()
def discovery(
    country: str = typer.Argument(..., help="ISO-3 country code, e.g. AUS, SGP, CHN"),
    keywords: str = typer.Option("", help="Search keywords"),
    pillars: list[int] = typer.Option([6, 7], help="RDTII pillars to search"),
    limit: int = typer.Option(10, min=1, max=50),
    browser_mode: str = typer.Option("auto", help="auto | playwright | opencli"),
) -> None:
    """Search official legal sources for a country."""
    # Resolve names / loose input against the configured country list, so
    # `stn discovery Singapore` works, not just `stn discovery SGP`.
    code = country.strip().upper()
    try:
        with _client(timeout=10.0) as client:
            configured = (
                client.get("/api/discovery/countries").json().get("countries", [])
            )
    except httpx.HTTPError:
        configured = []
    if configured:
        by_code = {c["country_code"].upper(): c for c in configured}
        by_label = {c["label"].upper(): c for c in configured}
        resolved = by_code.get(code) or by_label.get(code)
        if resolved:
            code = resolved["country_code"]
        else:
            table = Table(title="No discovery sources for that country — configured:")
            table.add_column("Code")
            table.add_column("Country")
            table.add_column("Sources")
            for c in sorted(configured, key=lambda x: x["country_code"]):
                table.add_row(
                    c["country_code"], c["label"], str(c.get("source_count", "—"))
                )
            console.print(table)
            raise typer.Exit(code=1)

    payload = {
        "country_code": code,
        "pillars": pillars,
        "keywords": keywords,
        "limit": limit,
        "browser_mode": browser_mode,
    }
    console.print(f"[dim]Searching {code} · pillars {pillars} · limit {limit}…[/]")
    try:
        with _client(timeout=180.0) as client:
            res = client.post("/api/discovery/search", json=payload)
    except httpx.HTTPError as exc:
        _die(f"Request failed: {exc}")
        return
    if res.status_code != 200:
        _die(f"HTTP {res.status_code}: {res.text[:300]}")
        return
    data = res.json()
    candidates = data.get("candidates", [])
    if not candidates:
        console.print("[yellow]No candidates found.[/]")
        return
    table = Table(title=f"Discovery · {code} · {len(candidates)} candidate(s)")
    table.add_column("Title", max_width=48, overflow="fold")
    table.add_column("Indicators")
    table.add_column("Grade")
    table.add_column("URL", max_width=52, overflow="fold", style="dim")
    for c in candidates:
        table.add_row(
            c.get("title") or "—",
            ",".join(c.get("matched_indicators", [])),
            str(c.get("source_grade", c.get("grade", "—"))),
            c.get("url", "—"),
        )
    console.print(table)


@app.command()
def rag(
    question: str = typer.Argument(..., help="Question for the knowledge base"),
    country: str = typer.Option("", help="Optional ISO-3 country filter"),
) -> None:
    """Ask the knowledge base."""
    inputs: dict = {"question": question}
    if country:
        inputs["country_code"] = country.upper()
    try:
        with _client(timeout=300.0) as client:
            res = client.post(
                "/api/workflows/nodes/rag.query/run",
                json={"node_id": "stn-cli", "inputs": inputs},
            )
    except httpx.HTTPError as exc:
        _die(f"Request failed: {exc}")
        return
    if res.status_code != 200:
        _die(f"HTTP {res.status_code}: {res.text[:300]}")
        return
    outputs = res.json().get("outputs", {})
    retrieved = outputs.get("retrieval_count", 0)
    provider = outputs.get("provider", "?")
    console.print(
        Panel(
            Markdown(outputs.get("answer", "(no answer)")),
            title=f"stn rag · {provider} · {retrieved} chunk(s) retrieved",
            border_style="cyan" if retrieved else "yellow",
            subtitle="" if retrieved else "⚠ ungrounded — no documents matched",
        )
    )


@app.command()
def docs() -> None:
    """List ingested documents."""
    try:
        with _client(timeout=15.0) as client:
            res = client.get("/api/canvas-files")
    except httpx.HTTPError as exc:
        _die(f"Request failed: {exc}")
        return
    if res.status_code == 401:
        _die("Authentication required — run `stn login` (token may have expired).")
        return
    if res.status_code != 200:
        _die(f"HTTP {res.status_code}: {res.text[:300]}")
        return
    docs_list = res.json()
    if not docs_list:
        console.print("[yellow]Knowledge base is empty.[/]")
        return
    table = Table(title=f"Knowledge base · {len(docs_list)} document(s)")
    table.add_column("Filename", max_width=42, overflow="fold")
    table.add_column("Status")
    table.add_column("Country")
    table.add_column("Ingested")
    table.add_column("ID", style="dim", max_width=14, overflow="fold")
    for d in docs_list:
        table.add_row(
            d.get("filename") or "—",
            d.get("status", "—"),
            d.get("country_code") or "—",
            (d.get("created_at") or "")[:10],
            d.get("document_id", "")[:12],
        )
    console.print(table)


@app.command("audit-countries")
def audit_countries(
    fix: bool = typer.Option(
        False, "--fix", help="Repair MISMATCH/missing rows (documents + embeddings)"
    ),
) -> None:
    """Audit stored country codes."""
    if fix and not typer.confirm(
        "Apply high-confidence country corrections to the database?"
    ):
        raise typer.Exit()
    try:
        with _client(timeout=120.0) as client:
            res = client.post("/api/canvas-files/audit-countries", params={"fix": fix})
    except httpx.HTTPError as exc:
        _die(f"Request failed: {exc}")
        return
    if res.status_code == 401:
        _die("Authentication required — run `stn login`.")
        return
    if res.status_code != 200:
        _die(f"HTTP {res.status_code}: {res.text[:300]}")
        return
    data = res.json()
    table = Table(title="Country audit" + (" · FIX APPLIED" if fix else " · read-only"))
    table.add_column("Filename", max_width=40, overflow="fold")
    table.add_column("Stored")
    table.add_column("Detected")
    table.add_column("Conf")
    table.add_column("Verdict")
    style_by_verdict = {
        "MISMATCH": "bold red",
        "missing-stored": "yellow",
        "match": "green",
        "undetected": "dim",
        "detected-not-in-registry": "magenta",
    }
    for e in data.get("report", []):
        verdict = e["verdict"] + (" → fixed" if e.get("fixed") else "")
        table.add_row(
            e.get("filename") or "—",
            e.get("stored") or "—",
            e.get("detected") or "—",
            f"{e.get('confidence', 0):.2f}",
            f"[{style_by_verdict.get(e['verdict'], '')}]{verdict}[/]",
        )
    console.print(table)
    s = data.get("summary", {})
    console.print(
        f"[bold]{s.get('documents', 0)}[/] documents · "
        f"[green]{s.get('match', 0)} match[/] · "
        f"[red]{s.get('mismatch', 0)} mismatch[/] · "
        f"[yellow]{s.get('missing_stored', 0)} missing[/] · "
        f"[dim]{s.get('undetected', 0)} undetected[/] · "
        f"[magenta]{s.get('not_in_registry', 0)} outside registry[/]"
        + (f" · [bold green]{s.get('fixed', 0)} fixed[/]" if fix else "")
    )


@app.command()
def tui() -> None:
    """Launch the SENTINEL terminal dashboard."""
    from .tui import run_tui

    run_tui(api=API, token=_auth_token())


if __name__ == "__main__":
    app()
