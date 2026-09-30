"""Options dialog. For now: the preset to load when the app starts."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QGroupBox, QHBoxLayout, QLineEdit,
                               QMessageBox, QPushButton, QVBoxLayout)

from ..i18n import tr
from .settings import set_startup_preset, startup_preset_setting


class OptionsDialog(QDialog):
    def __init__(self, preset_dir: Path, parent=None):
        """`preset_dir`: where "Browse…" starts when no startup preset is set yet."""
        super().__init__(parent)
        self.setWindowTitle(tr("Options"))
        self.preset_dir = preset_dir
        enabled, path = startup_preset_setting()

        self.startup_check = QCheckBox(tr("Load a preset at startup"))
        self.startup_check.setChecked(enabled)
        self.startup_check.toggled.connect(self._sync_enabled)
        self.startup_path = QLineEdit(path)
        self.startup_path.setPlaceholderText(tr("Preset file (.json)"))
        self.browse_btn = QPushButton(tr("Browse…"))
        self.browse_btn.clicked.connect(self._browse)

        row = QHBoxLayout()
        row.addWidget(self.startup_path, 1)
        row.addWidget(self.browse_btn)
        startup = QGroupBox(tr("Startup"))
        group = QVBoxLayout(startup)
        group.addWidget(self.startup_check)
        group.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(startup)
        layout.addStretch(1)
        layout.addWidget(buttons)
        self.resize(560, self.sizeHint().height())
        self._sync_enabled()

    def _sync_enabled(self) -> None:
        on = self.startup_check.isChecked()
        self.startup_path.setEnabled(on)
        self.browse_btn.setEnabled(on)

    def _browse(self) -> None:
        start = self.startup_path.text().strip() or str(self.preset_dir)
        path, _ = QFileDialog.getOpenFileName(self, tr("Preset to load at startup"), start,
                                              tr("simpleVCam presets (*.json)"))
        if path:
            self.startup_path.setText(str(Path(path)))

    def accept(self) -> None:
        enabled, path = self.startup_check.isChecked(), self.startup_path.text().strip()
        if enabled and not path:
            QMessageBox.warning(self, "simpleVCam", tr("Choose the preset to load at startup."))
            return
        set_startup_preset(enabled, path)
        super().accept()
