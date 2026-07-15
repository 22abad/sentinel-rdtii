"""Shared CLI progress UI for the command-line tools (main.py, discovery).

A single-line, self-contained dual progress bar drawn on stderr: OVERALL
progress (e.g. pillars) and CURRENT-STEP progress (e.g. documents), plus a live
label of what's happening — so a demo/judge sees continuous motion instead of a
silent hang. Pure ASCII, no dependency; stdout (the CSV/JSON) is never touched.
"""

from __future__ import annotations

import sys


class ProgressUI:
    """Dual single-line progress bar on stderr. Use only when stderr is a TTY."""

    def __init__(self, total_units: int, unit: str = "pillars") -> None:
        self.total_units = max(1, total_units)
        self.done_units = 0
        self.unit = unit
        self.context: str | None = None
        self.step_n = 0
        self.step_total = 1
        self.label = "starting…"
        self._last_len = 0

    @staticmethod
    def _bar(n: int, total: int, width: int = 14) -> str:
        total = max(1, total)
        filled = int(round(width * min(max(n, 0), total) / total))
        return "#" * filled + "-" * (width - filled)

    def _render(self) -> None:
        line = (
            f"Overall [{self._bar(self.done_units, self.total_units)}] "
            f"{self.done_units}/{self.total_units} {self.unit}  "
            f"Step [{self._bar(self.step_n, self.step_total)}] "
            f"{self.step_n}/{self.step_total}  {self.label}"
        )
        pad = max(0, self._last_len - len(line))
        sys.stderr.write("\r" + line + " " * pad)
        sys.stderr.flush()
        self._last_len = len(line)

    def start_unit(self, context) -> None:
        """Begin a new overall unit (e.g. a pillar); resets the step bar."""
        self.context = context
        self.step_n, self.step_total = 0, 1
        self.label = f"{context}: starting…"
        self._render()

    def on_progress(self, label: str, current=None, total=None) -> None:
        if total:
            self.step_total = total
        if current is not None:
            self.step_n = current
        prefix = f"{self.context}: " if self.context is not None else ""
        self.label = (prefix + (label or ""))[:64]
        self._render()

    def unit_done(self) -> None:
        self.done_units = min(self.done_units + 1, self.total_units)
        self.step_n = self.step_total
        self._render()

    def log(self, message: str) -> None:
        """Print a scrolling log line above the bar without corrupting it."""
        sys.stderr.write("\r" + " " * self._last_len + "\r")
        self._last_len = 0
        print(message, file=sys.stderr, flush=True)
        self._render()

    def close(self) -> None:
        sys.stderr.write("\n")
        sys.stderr.flush()


def make_progress_ui(total_units: int, unit: str = "pillars"):
    """Return a ProgressUI if stderr is an interactive TTY, else None.

    The caller uses ``None`` to fall back to plain narration lines, keeping
    piped/redirected output clean.
    """
    if not sys.stderr.isatty():
        return None
    try:
        return ProgressUI(total_units, unit=unit)
    except Exception:  # pragma: no cover — never let the UI break a real run
        return None
