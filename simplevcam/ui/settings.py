"""Choices remembered between sessions (HKCU\\Software\\simpleVCam)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings


def settings() -> QSettings:
    return QSettings("simpleVCam", "simpleVCam")


def startup_preset_setting() -> tuple[bool, str]:
    """(load a preset at startup, its path), as set in the options."""
    s = settings()
    return s.value("startup_preset_enabled", False, type=bool), s.value("startup_preset_path", "", type=str)


def set_startup_preset(enabled: bool, path: str) -> None:
    s = settings()
    s.setValue("startup_preset_enabled", enabled)
    s.setValue("startup_preset_path", path)


def startup_preset() -> Path | None:
    """The preset to load at startup, or None if the option is off."""
    enabled, path = startup_preset_setting()
    return Path(path) if enabled and path else None


def animations_panel_visible() -> bool:
    return settings().value("animations_panel_visible", False, type=bool)


def set_animations_panel_visible(visible: bool) -> None:
    settings().setValue("animations_panel_visible", visible)
