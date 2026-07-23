"""Tests for user theming (stn_cli.theme) — merge precedence, transparency,
alpha passthrough, and resilience to broken files."""

from __future__ import annotations

from pathlib import Path

from stn_cli.theme import PALETTE_DEFAULTS, ThemeConfig, config_path, load_config


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "theme.toml"
    path.write_text(body)
    return path


def test_missing_file_gives_defaults(tmp_path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.palette == PALETTE_DEFAULTS
    assert cfg.dark is True
    assert cfg.transparent is False
    assert cfg.phases == ("thinking", "retrieving", "reranking", "drafting")


def test_partial_file_overrides_only_named_keys(tmp_path):
    # The exact shape of a real user file: transparency + alpha layers.
    path = _write(
        tmp_path,
        """
        [palette]
        transparent = true
        surface = "#13201bCC"
        panel   = "#182721B3"

        [widgets]
        chat_message_opacity = 1.0
        """,
    )
    cfg = load_config(path)
    assert cfg.transparent is True
    assert cfg.palette["surface"] == "#13201bCC"
    assert cfg.palette["panel"] == "#182721B3"
    # Untouched keys keep the SENTINEL defaults.
    assert cfg.palette["primary"] == PALETTE_DEFAULTS["primary"]
    assert cfg.chat_message_opacity == 1.0


def test_env_overrides_beat_file(tmp_path, monkeypatch):
    path = _write(tmp_path, '[palette]\nprimary = "#ff0000"\n')
    monkeypatch.setenv("STN_THEME_PRIMARY", "#00ff00")
    monkeypatch.setenv("STN_THEME_TRANSPARENT", "yes")
    cfg = load_config(path)
    assert cfg.palette["primary"] == "#00ff00"
    assert cfg.transparent is True


def test_broken_toml_falls_back_to_defaults(tmp_path, capsys):
    path = _write(tmp_path, "[palette\nnot toml at all")
    cfg = load_config(path)
    assert cfg.palette == PALETTE_DEFAULTS
    assert "ignoring bad theme file" in capsys.readouterr().err


def test_thinking_overrides(tmp_path):
    path = _write(
        tmp_path,
        """
        [thinking]
        spinner = "◐◓◑◒"
        phases = ["pondering", "cooking"]
        phase_secs = 1.5
        """,
    )
    cfg = load_config(path)
    assert cfg.spinner == "◐◓◑◒"
    assert cfg.phases == ("pondering", "cooking")
    assert cfg.phase_secs == 1.5


def test_transparent_swaps_background_to_ansi_default():
    cfg = ThemeConfig(transparent=True)
    assert cfg.to_theme().background == "ansi_default"
    # Opaque config keeps the palette background.
    assert ThemeConfig().to_theme().background == PALETTE_DEFAULTS["background"]


def test_alpha_hex_survives_into_theme():
    cfg = ThemeConfig()
    cfg.palette["surface"] = "#13201bCC"
    assert cfg.to_theme().surface == "#13201bCC"


def test_rich_accessor_strips_alpha():
    # Rich's Color.parse rejects 8-digit hex — Style(bgcolor=…) crashed on an
    # alpha'd surface until .rich() stripped it. Textual keeps the alpha.
    cfg = ThemeConfig()
    cfg.palette["surface"] = "#13201bCC"
    assert cfg.rich("surface") == "#13201b"
    assert cfg.rich("primary") == cfg.palette["primary"]  # 6-digit untouched
    from rich.style import Style

    Style(bgcolor=cfg.rich("surface"))  # must not raise


def test_opacity_clamped(tmp_path):
    path = _write(tmp_path, "[widgets]\nchat_message_opacity = 7.5\n")
    assert load_config(path).chat_message_opacity == 1.0
    path = _write(tmp_path, "[widgets]\nchat_message_opacity = -2\n")
    assert load_config(path).chat_message_opacity == 0.0


def test_config_path_resolution(monkeypatch, tmp_path):
    monkeypatch.setenv("STN_CONFIG", str(tmp_path / "explicit.toml"))
    assert config_path() == tmp_path / "explicit.toml"
    monkeypatch.delenv("STN_CONFIG")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert config_path() == tmp_path / "xdg" / "stn" / "theme.toml"
    monkeypatch.delenv("XDG_CONFIG_HOME")
    assert config_path() == Path.home() / ".config" / "stn" / "theme.toml"


def test_bad_value_types_ignored(tmp_path):
    path = _write(
        tmp_path,
        """
        [palette]
        primary = 42
        transparent = "yes-string"

        [thinking]
        phase_secs = -3
        phases = []
        """,
    )
    cfg = load_config(path)
    assert cfg.palette["primary"] == PALETTE_DEFAULTS["primary"]
    assert cfg.transparent is False
    assert cfg.phase_secs == 3.0
    assert len(cfg.phases) == 4
