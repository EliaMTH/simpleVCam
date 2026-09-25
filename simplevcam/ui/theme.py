"""Dark theme: Fusion style with a dark palette (independent of the Windows theme)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

TEXT = QColor(230, 230, 233)
DISABLED_TEXT = QColor(125, 125, 132)


def apply_dark_theme(app: QApplication) -> None:
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):  # Qt >= 6.8: also makes the Windows title bar dark
        hints.setColorScheme(Qt.ColorScheme.Dark)
    app.setStyle("Fusion")

    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: QColor(40, 42, 48),
        QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: QColor(28, 30, 34),
        QPalette.ColorRole.AlternateBase: QColor(44, 46, 52),
        QPalette.ColorRole.ToolTipBase: QColor(50, 52, 58),
        QPalette.ColorRole.ToolTipText: TEXT,
        QPalette.ColorRole.PlaceholderText: QColor(140, 140, 148),
        QPalette.ColorRole.Text: TEXT,
        QPalette.ColorRole.Button: QColor(52, 55, 62),
        QPalette.ColorRole.ButtonText: TEXT,
        QPalette.ColorRole.BrightText: QColor(255, 90, 90),
        QPalette.ColorRole.Link: QColor(90, 160, 255),
        QPalette.ColorRole.Highlight: QColor(58, 120, 215),
        QPalette.ColorRole.HighlightedText: QColor(255, 255, 255),
        QPalette.ColorRole.Light: QColor(70, 73, 82),
        QPalette.ColorRole.Midlight: QColor(58, 61, 68),
        QPalette.ColorRole.Mid: QColor(36, 38, 43),
        QPalette.ColorRole.Dark: QColor(24, 25, 29),
        QPalette.ColorRole.Shadow: QColor(10, 10, 12),
    }
    for role, color in roles.items():
        p.setColor(role, color)
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, DISABLED_TEXT)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(44, 46, 52))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(70, 73, 82))
    app.setPalette(p)
    app.setStyleSheet("QToolTip { color: #e6e6e9; background: #32343a; border: 1px solid #50535c; }")
