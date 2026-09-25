"""Main window: top bar with presets, output format and camera switch; preview and layer panel below."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
                               QSplitter, QVBoxLayout, QWidget)

from ..engine import Engine
from ..model import Layer, OutputSettings
from ..presets import load_preset, save_preset
from .. import __version__
from ..vcam import VCamError, not_installed_message
from .add_source_dialog import AddSourceDialog
from .layers_panel import LayersPanel
from .mask_editor import MaskEditorDialog
from .preview import PreviewWidget

RESOLUTIONS = [(640, 360), (640, 480), (854, 480), (1280, 720), (1920, 1080)]
FRAME_RATES = [15, 30, 60, 120]


def default_preset_dir() -> Path:
    if getattr(sys, "frozen", False):  # packaged executable
        return Path.home() / "Documents" / "simpleVCam"
    return Path(__file__).resolve().parents[2] / "presets"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"simpleVCam {__version__}")
        self.resize(1400, 820)
        self.preset_path: Path | None = None

        self.engine = Engine()
        self.preview = PreviewWidget(self.engine)
        self.panel = LayersPanel(self.engine)
        self.panel.setMinimumWidth(340)

        splitter = QSplitter()
        splitter.addWidget(self.preview)
        splitter.addWidget(self.panel)
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([1040, 360])

        # top bar
        save_btn = QPushButton("Salva preset…")
        save_btn.clicked.connect(self.save_preset)
        load_btn = QPushButton("Carica preset…")
        load_btn.clicked.connect(self.load_preset)

        self.resolution = QComboBox()
        for w, h in RESOLUTIONS:
            self.resolution.addItem(f"{w}×{h}", (w, h))
        self.mirror = QCheckBox("Specchia uscita")
        self.mirror.setToolTip("Specchia orizzontalmente tutta l'immagine inviata alla camera (e l'anteprima)")
        self.fps = QComboBox()
        for fps in FRAME_RATES:
            self.fps.addItem(f"{fps} fps", fps)
        self._show_output(self.engine.scene.output)
        self.resolution.currentIndexChanged.connect(self._on_output_changed)
        self.fps.currentIndexChanged.connect(self._on_output_changed)
        self.mirror.toggled.connect(self._on_output_changed)

        self.camera_btn = QPushButton()
        self.camera_btn.setCheckable(True)
        self.camera_btn.setMinimumWidth(170)
        self.camera_btn.toggled.connect(self._on_camera_toggled)
        self.camera_label = QLabel()
        self._show_camera_state()

        bar = QHBoxLayout()
        bar.addWidget(save_btn)
        bar.addWidget(load_btn)
        bar.addSpacing(24)
        bar.addWidget(QLabel("Output:"))
        bar.addWidget(self.resolution)
        bar.addWidget(self.fps)
        bar.addSpacing(12)
        bar.addWidget(self.mirror)
        bar.addStretch(1)
        bar.addWidget(self.camera_label)
        bar.addWidget(self.camera_btn)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(bar)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(central)
        self.fps_label = QLabel()
        self.statusBar().addPermanentWidget(self.fps_label)

        # wiring
        self.engine.preview_ready.connect(self.preview.set_image)
        self.engine.layers_changed.connect(self.panel.refresh)
        self.engine.fps_measured.connect(lambda fps: self.fps_label.setText(f"{fps:.1f} fps"))
        self.preview.layer_selected.connect(self.panel.select)
        self.preview.layer_edited.connect(self.panel.refresh)
        self.panel.selection_changed.connect(self.preview.set_selected)
        self.panel.add_requested.connect(self.add_layer)
        self.panel.remove_requested.connect(self.remove_layer)
        self.panel.move_requested.connect(self.move_layer)
        self.panel.order_changed.connect(self.engine.set_layer_order)
        self.panel.mask_requested.connect(self.edit_mask)

        # slow refresh of things that change on their own (source sizes and errors, camera connection)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._periodic)
        self.timer.start(300)

        self.engine.start()
        if not self.engine.camera.available:
            self.statusBar().showMessage(not_installed_message())

    # --- layers ----------------------------------------------------------------

    def add_layer(self) -> None:
        dialog = AddSourceDialog(self)
        if not dialog.exec():
            return
        result = dialog.result_spec()
        if result is None:
            QMessageBox.warning(self, "simpleVCam", "Nessuna sorgente selezionata.")
            return
        spec, name = result
        layer = Layer(spec, name)
        self.engine.add_layer(layer)
        self.panel.rebuild(select_id=layer.id)

    def remove_layer(self, layer_id: str) -> None:
        self.engine.remove_layer(layer_id)
        self.panel.rebuild()

    def move_layer(self, layer_id: str, delta: int) -> None:
        self.engine.move_layer(layer_id, delta)
        self.panel.rebuild(select_id=layer_id)

    def edit_mask(self, layer_id: str) -> None:
        layer = self.engine.scene.layer_by_id(layer_id)
        if layer is None:
            return
        frame = self.engine.latest_frame(layer_id)
        if frame is None and layer.source_size is None and layer.mask is None:
            QMessageBox.information(self, "simpleVCam", "La sorgente non ha ancora prodotto immagini: la mask ha bisogno delle sue dimensioni.")
            return
        dialog = MaskEditorDialog(layer, frame.copy() if frame is not None else None, self)
        if dialog.exec():
            layer.set_mask(dialog.result_mask())
            self.panel.refresh()

    # --- presets ---------------------------------------------------------------

    def save_preset(self) -> None:
        folder = default_preset_dir()
        folder.mkdir(parents=True, exist_ok=True)
        start = str(self.preset_path or folder / "preset.json")
        path, _ = QFileDialog.getSaveFileName(self, "Salva preset", start, "Preset simpleVCam (*.json)")
        if not path:
            return
        try:
            save_preset(self.engine.scene, path)
        except Exception as e:
            QMessageBox.critical(self, "simpleVCam", f"Salvataggio non riuscito:\n{e}")
            return
        self.preset_path = Path(path)
        self.statusBar().showMessage(f"Preset salvato: {path}", 5000)

    def load_preset(self) -> None:
        start = str(self.preset_path.parent if self.preset_path else default_preset_dir())
        path, _ = QFileDialog.getOpenFileName(self, "Carica preset", start, "Preset simpleVCam (*.json)")
        if not path:
            return
        try:
            scene = load_preset(path)
        except Exception as e:
            QMessageBox.critical(self, "simpleVCam", f"Caricamento non riuscito:\n{e}")
            return
        try:
            self.engine.set_scene(scene)
        except VCamError as e:
            self._camera_failed(e)
        self.preset_path = Path(path)
        self._show_output(scene.output)
        self.panel.rebuild()
        self.statusBar().showMessage(f"Preset caricato: {path}", 5000)

    # --- output and camera -----------------------------------------------------

    def _show_output(self, output: OutputSettings) -> None:
        for widget in (self.resolution, self.fps, self.mirror):
            widget.blockSignals(True)
        index = self.resolution.findData((output.width, output.height))
        if index < 0:
            self.resolution.addItem(f"{output.width}×{output.height}", (output.width, output.height))
            index = self.resolution.count() - 1
        self.resolution.setCurrentIndex(index)
        index = self.fps.findData(output.fps)
        if index < 0:  # e.g. a preset saved with 25 fps
            self.fps.addItem(f"{output.fps} fps", output.fps)
            index = self.fps.count() - 1
        self.fps.setCurrentIndex(index)
        self.mirror.setChecked(output.mirror)
        for widget in (self.resolution, self.fps, self.mirror):
            widget.blockSignals(False)

    def _on_output_changed(self) -> None:
        w, h = self.resolution.currentData()
        output = OutputSettings(w, h, self.fps.currentData(), self.mirror.isChecked())
        if output == self.engine.scene.output:
            return
        try:
            self.engine.set_output(output)
        except VCamError as e:
            self._camera_failed(e)

    def _on_camera_toggled(self, on: bool) -> None:
        try:
            if on:
                self.engine.start_camera()
            else:
                self.engine.stop_camera()
        except VCamError as e:
            self._camera_failed(e)
        self._show_camera_state()

    def _camera_failed(self, error: Exception) -> None:
        self.camera_btn.blockSignals(True)
        self.camera_btn.setChecked(False)
        self.camera_btn.blockSignals(False)
        self._show_camera_state()
        QMessageBox.critical(self, "simpleVCam", str(error))

    def _show_camera_state(self) -> None:
        running = self.engine.camera_running
        if not running:
            text, color = "Camera spenta", "gray"
        elif self.engine.camera_connected:
            text, color = "Camera accesa — in uso", "#3cb96a"
        else:
            text, color = "Camera accesa — nessuna app collegata", "#e0a030"
        state = (running, text)
        if state == getattr(self, "_camera_state", None):
            return  # called periodically: avoid re-applying style sheets
        self._camera_state = state

        self.camera_btn.setText("■  Ferma camera" if running else "●  Avvia camera")
        button = "#c0392b" if running else "#2e8b57"  # red: stop, green: start
        self.camera_btn.setStyleSheet(f"QPushButton {{ color: white; background: {button}; font-weight: bold; padding: 6px; "
                                      f"border: 1px solid #1c1d21; border-radius: 4px; }}")
        self.camera_label.setText(text)
        self.camera_label.setStyleSheet(f"color: {color}")

    def _periodic(self) -> None:
        self.panel.refresh()
        self._show_camera_state()

    def closeEvent(self, event) -> None:
        self.timer.stop()
        self.engine.shutdown()
        super().closeEvent(event)
