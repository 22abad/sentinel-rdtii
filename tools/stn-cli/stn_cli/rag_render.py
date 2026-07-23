"""Terminal rendering for RAG answers — a customized `stn tui` module.

The backend RAG node returns an answer shaped for a *web* view: Markdown with
`##` headings, `**bold**`, `-` bullets, `>` blockquotes, `[label](url)` links,
and RDTII references (`P6`, indicator `7.3`). In the browser that renders as
HTML; in the TUI, `ChatMessage` used to `escape()` it verbatim, so the analyst
saw literal `**` and `##`.

`render_answer` closes that gap: it turns the web-oriented Markdown into
SENTINEL-themed Rich console markup, tuned to the emerald/teal palette used by
the rest of the dashboard, with domain-aware highlighting of pillar/indicator
references. Every span of model text is `escape()`d before any markup tag is
injected, so a stray `[` in the answer can never break the render (it is in
fact safer than the old raw-escape path).

The primitives (`render_markdown`, `inline`) are reusable by any other pane
that needs to show model-authored Markdown in the terminal.
"""

from __future__ import annotations

import re

from rich.markup import escape

# SENTINEL palette (mirrors tui.py's SENTINEL_THEME).
_ACCENT = "#10B981"  # emerald — headers, list markers, quote bars
_HILITE = "#34d399"  # lighter emerald — inline domain refs, link labels
_MUTED = "#bec7c3"  # body-dim, quoted legal text
_RULE = "#2a3a33"  # horizontal rule


def _h(title: str, color: str = "#e7efec") -> str:
    """Section header: accent side-bar + bright title (matches tui.py `_h`)."""
    return f"[bold {_ACCENT}]▍[/][bold {color}] {title}[/]"


# ── inline spans ──────────────────────────────────────────────────────────
# One pass, leftmost match wins. `bold` precedes `italic` so `**x**` is not
# eaten as two italics. Underscore emphasis is boundary-guarded so identifiers
# like `source_file_sha256` are NOT italicised.
_INLINE = re.compile(
    r"(?P<code>`[^`]+`)"
    r"|(?P<bold>\*\*.+?\*\*|(?<!\w)__.+?__(?!\w))"
    r"|(?P<italic>\*(?!\s).+?(?<!\s)\*|(?<!\w)_(?!\s).+?(?<!\s)_(?!\w))"
    r"|(?P<link>\[[^\]]+\]\([^)]+\))"
    r"|(?P<url>https?://[^\s)\]]+)"
)

# RDTII references worth surfacing: pillars (P6 / Pillar 6) and dotted
# indicators (6.1, 7.3, 12.10). Indicators start 1–12, so a score like 0.5 is
# deliberately excluded — only real indicator numbers light up.
_DOMAIN = re.compile(
    r"(?<![\w.])(?:P(?:illar\s*)?(?:1[0-2]|[1-9])|(?:1[0-2]|[1-9])\.\d{1,2})(?![\w])"
)

_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _domain(escaped: str) -> str:
    """Highlight pillar/indicator references inside already-escaped text."""
    return _DOMAIN.sub(lambda m: f"[bold {_HILITE}]{m.group()}[/]", escaped)


def inline(text: str) -> str:
    """Render one line of inline Markdown to Rich markup (text is escaped)."""
    out: list[str] = []
    pos = 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            out.append(_domain(escape(text[pos : m.start()])))
        kind, val = m.lastgroup, m.group()
        if kind == "code":
            out.append(f"[reverse] {escape(val[1:-1])} [/]")
        elif kind == "bold":
            inner = val[2:-2]
            out.append(f"[bold]{_domain(escape(inner))}[/]")
        elif kind == "italic":
            inner = val[1:-1]
            out.append(f"[italic]{_domain(escape(inner))}[/]")
        elif kind == "link":
            lm = _LINK.match(val)
            if lm:
                label, url = lm.group(1), lm.group(2)
                out.append(f"[u {_HILITE}]{escape(label)}[/] [dim]({escape(url)})[/]")
        elif kind == "url":
            out.append(f"[dim underline]{escape(val)}[/]")
        pos = m.end()
    if pos < len(text):
        out.append(_domain(escape(text[pos:])))
    return "".join(out)


# ── block structure ───────────────────────────────────────────────────────
_HEADING = re.compile(r"(#{1,6})\s+(.*)")
_BULLET = re.compile(r"[-*+]\s+(.*)")
_NUMBERED = re.compile(r"(\d+)\.\s+(.*)")  # dot+space → list; `6.1` (no space) is not
_HRULE = re.compile(r"(-{3,}|\*{3,}|_{3,})")


def render_markdown(raw: str) -> str:
    """Convert model-authored Markdown to SENTINEL-themed Rich markup."""
    out: list[str] = []
    in_code = False
    for line in raw.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            out.append(f"[dim]{escape(line)}[/]")
            continue

        if not stripped:
            out.append("")
            continue

        if _HRULE.fullmatch(stripped):
            out.append(f"[{_RULE}]{'─' * 48}[/]")
            continue

        m = _HEADING.match(stripped)
        if m:
            out.append("")
            out.append(_h(inline(m.group(2))))
            continue

        if stripped.startswith(">"):
            quote = stripped.lstrip(">").strip()
            out.append(f"[{_ACCENT}]▏[/] [italic {_MUTED}]{inline(quote)}[/]")
            continue

        m = _BULLET.match(stripped)
        if m:
            out.append(f"  [{_ACCENT}]•[/] {inline(m.group(1))}")
            continue

        m = _NUMBERED.match(stripped)
        if m:
            out.append(f"  [{_ACCENT}]{m.group(1)}.[/] {inline(m.group(2))}")
            continue

        out.append(inline(stripped))

    # trim leading/trailing blank lines the transforms may introduce
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


# Public name the TUI imports; a thin alias so the intent reads clearly at the
# call site (this is specifically the assistant's answer, not arbitrary text).
render_answer = render_markdown
