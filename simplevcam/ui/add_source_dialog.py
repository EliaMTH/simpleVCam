"""Dialog to pick a new source: a monitor, a window, an image file or a webcam."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from ..model import SourceSpec
from ..sources.winutil import list_monitors, list_webcams, list_windows

IMAGE_FILTER = "Immagini (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;Tutti i file (*)"


class AddSourceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aggiungi sorgente")
        self.resize(560, 420)

        self.screens = QListWidget()
        self.windows = QListWidget()
        self.webcams = QListWidget()
        self.image_path = QLineEdit()
        self.image_path.setPlaceholderText("Percorso dell'immagine")
        self.name_edit = QLineEdit()

        refresh = QPushButton("Aggiorna elenco")
        refresh.clicked.connect(self._fill_windows)
        windows_page = QWidget()
        wl = QVBoxLayout(windows_page)
        wl.addWidget(self.windows)
        wl.addWidget(refresh, 0, Qt.AlignmentFlag.AlignRight)

        browse = QPushButton("Sfoglia…")
        browse.clicked.connect(self._browse_image)
        image_page = QWidget()
        il = QVBoxLayout(image_page)
        row = QHBoxLayout()
        row.addWidget(self.image_path)
        row.addWidget(browse)
        il.addLayout(row)
        il.addStretch(1)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.screens, "Schermo")
        self.tabs.addTab(windows_page, "Finestra")
        self.tabs.addTab(image_page, "Immagine")
        self.tabs.addTab(self.webcams, "Webcam")
        self.tabs.currentChanged.connect(self._suggest_name)

        for lst in (self.screens, self.windows, self.webcams):
            lst.currentItemChanged.connect(self._suggest_name)
            lst.itemDoubleClicked.connect(self.accept)
        self.image_path.textChanged.connect(self._suggest_name)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Nome del layer", self.name_edit)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self._fill_screens()
        self._fill_windows()
        self._fill_webcams()
        self._suggest_name()

    def _fill_screens(self) -> None:
        self.screens.clear()
        for m in list_monitors():
            item = QListWidgetItem(m.label)
            item.setData(Qt.ItemDataRole.UserRole, m)
            self.screens.addItem(item)
        self.screens.setCurrentRow(0)

    def _fill_windows(self) -> None:
        self.windows.clear()
        for w in list_windows():
            item = QListWidgetItem(w.label)
            item.setData(Qt.ItemDataRole.UserRole, w)
            self.windows.addItem(item)
        self.windows.setCurrentRow(0)

    def _fill_webcams(self) -> None:
        self.webcams.clear()
        for cam in list_webcams():
            item = QListWidgetItem(cam.name)
            item.setData(Qt.ItemDataRole.UserRole, cam)
            self.webcams.addItem(item)
        self.webcams.setCurrentRow(0)

    def _browse_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Scegli un'immagine", self.image_path.text(), IMAGE_FILTER)
        if path:
            self.image_path.setText(path)

    def _current_data(self, lst: QListWidget):
        item = lst.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _suggest_name(self, *_) -> None:
        page = self.tabs.currentIndex()
        name = ""
        if page == 0 and (m := self._current_data(self.screens)):
            name = f"Schermo {m.index}"
        elif page == 1 and (w := self._current_data(self.windows)):
            name = w.title[:40]
        elif page == 2 and self.image_path.text():
            name = Path(self.image_path.text()).stem
        elif page == 3 and (cam := self._current_data(self.webcams)):
            name = cam.name
        self.name_edit.setText(name)

    def result_spec(self) -> tuple[SourceSpec, str] | None:
        """The chosen source and layer name, or None if nothing valid was selected."""
        page = self.tabs.currentIndex()
        spec = None
        if page == 0 and (m := self._current_data(self.screens)):
            spec = SourceSpec("screen", monitor=m.index)
        elif page == 1 and (w := self._current_data(self.windows)):
            spec = SourceSpec("window", title=w.title, exe=w.exe)
            spec.hwnd = w.hwnd
        elif page == 2 and self.image_path.text().strip():
            spec = SourceSpec("image", path=Path(self.image_path.text().strip()).as_posix())  # readable in JSON
        elif page == 3 and (cam := self._current_data(self.webcams)):
            spec = SourceSpec("webcam", index=cam.index, name=cam.name)
        if spec is None:
            return None
        return spec, self.name_edit.text().strip() or spec.type
