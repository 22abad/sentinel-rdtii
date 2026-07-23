"""User theming — `theme.toml` overrides layered on the SENTINEL defaults.

Resolution order for the file (first hit wins):
  1. ``$STN_CONFIG``            — explicit path to a theme.toml
  2. ``$XDG_CONFIG_HOME/stn/theme.toml``
  3. ``~/.config/stn/theme.toml``   (same home as credentials.json)

Precedence for each value: code defaults < theme.toml < ``STN_THEME_*`` env
vars. Env override keeps the Docker path mount-free — compose sets
``STN_THEME_PRIMARY`` etc. without needing the file in the container.

``transparent = true`` swaps the background for the terminal's own default
color (``ansi_default``) so the emulator's opacity/blur shows through; pair
it with 8-digit alpha hexes on ``surface``/``panel`` for the layered look.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from textual.theme import Theme

_HEX_ALPHA = re.compile(r"^#([0-9a-fA-F]{6})[0-9a-fA-F]{2}$")


def rich_color(value: str) -> str:
    """A palette color, safe for Rich contexts (inline markup, ``Style``).

    Textual's Color parses 8-digit alpha hex; Rich's does NOT — so alpha
    belongs only in the Textual theme, and Rich consumers get the opaque
    6-digit base.
    """
    match = _HEX_ALPHA.match(value.strip())
    return f"#{match.group(1)}" if match else value

# The 10 color slots Theme accepts, with the SENTINEL emerald defaults.
# (tui.py's SENTINEL_THEME is built from exactly this dict.)
PALETTE_DEFAULTS: dict[str, str] = {
    "primary": "#10B981",
    "secondary": "#0f766e",
    "accent": "#10B981",
    "success": "#10B981",
    "warning": "#f59e0b",
    "error": "#dc2626",
    "foreground": "#e7efec",
    "background": "#0c1210",
    "surface": "#13201b",
    "panel": "#182721",
}


@dataclass
class ThemeConfig:
    """Everything the TUI reads at startup, post-merge."""

    palette: dict[str, str] = field(default_factory=lambda: dict(PALETTE_DEFAULTS))
    dark: bool = True
    transparent: bool = False
    # [thinking]
    spinner: str = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    phases: tuple[str, ...] = ("thinking", "retrieving", "reranking", "drafting")
    phase_secs: float = 3.0
    # [chat]
    you_marker: str = ""  # empty = palette primary
    stn_marker: str = "cyan"
    # [widgets]
    chat_message_opacity: float = 1.0

    @property
    def primary(self) -> str:
        return self.palette["primary"]

    def rich(self, key: str) -> str:
        """Palette color for Rich markup/Style use (alpha stripped)."""
        return rich_color(self.palette[key])

    def to_theme(self) -> Theme:
        """The merged palette as a registered Textual theme."""
        palette = dict(self.palette)
        if self.transparent:
            # Terminal-default background — the emulator's opacity/blur shows
            # through (the app must also set App.ansi_color = True).
            palette["background"] = "ansi_default"
        return Theme(name="sentinel", dark=self.dark, **palette)


def config_path() -> Path:
    """Where theme.toml lives for this invocation (may not exist)."""
    if explicit := os.getenv("STN_CONFIG"):
        return Path(explicit).expanduser()
    xdg = os.getenv("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "stn" / "theme.toml"


def _load_toml(path: Path) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}
    except (tomllib.TOMLDecodeError, OSError) as exc:
        # A broken theme must never take the TUI down — fall back loudly.
        import sys

        print(f"stn: ignoring bad theme file {path}: {exc}", file=sys.stderr)
        return {}


def load_config(path: Path | None = None) -> ThemeConfig:
    """Defaults < theme.toml < STN_THEME_* env vars."""
    raw = _load_toml(path if path is not None else config_path())
    cfg = ThemeConfig()

    pal = raw.get("palette", {})
    for key in PALETTE_DEFAULTS:
        if isinstance(pal.get(key), str):
            cfg.palette[key] = pal[key]
    if isinstance(pal.get("dark"), bool):
        cfg.dark = pal["dark"]
    if isinstance(pal.get("transparent"), bool):
        cfg.transparent = pal["transparent"]

    think = raw.get("thinking", {})
    if isinstance(think.get("spinner"), str) and think["spinner"]:
        cfg.spinner = think["spinner"]
    if isinstance(think.get("phases"), list) and think["phases"]:
        cfg.phases = tuple(str(p) for p in think["phases"])
    if isinstance(think.get("phase_secs"), (int, float)) and think["phase_secs"] > 0:
        cfg.phase_secs = float(think["phase_secs"])

    chat = raw.get("chat", {})
    if isinstance(chat.get("you_marker"), str):
        cfg.you_marker = chat["you_marker"]
    if isinstance(chat.get("stn_marker"), str) and chat["stn_marker"]:
        cfg.stn_marker = chat["stn_marker"]

    widgets = raw.get("widgets", {})
    if isinstance(widgets.get("chat_message_opacity"), (int, float)):
        cfg.chat_message_opacity = min(1.0, max(0.0, float(widgets["chat_message_opacity"])))

    _apply_env_overrides(cfg)
    return cfg


def _apply_env_overrides(cfg: ThemeConfig) -> None:
    """STN_THEME_<PALETTE_KEY>, STN_THEME_DARK, STN_THEME_TRANSPARENT."""
    for key in PALETTE_DEFAULTS:
        if value := os.getenv(f"STN_THEME_{key.upper()}"):
            cfg.palette[key] = value
    for flag in ("dark", "transparent"):
        if value := os.getenv(f"STN_THEME_{flag.upper()}"):
            setattr(cfg, flag, value.strip().lower() in {"1", "true", "yes", "on"})
