"""Position, size, mirroring and crop of a layer: the properties shared by the scene layers and the animations."""
from __future__ import annotations

from PySide6.QtWidgets import (QAbstractSpinBox, QCheckBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

from ..engine import Engine
from ..i18n import tr
from ..model import Crop, Layer


def _spin(minimum: float, maximum: float) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(0)
    box.setKeyboardTracking(False)
    box.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    return box


class GeometryEditor(QWidget):
    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.layer: Layer | None = None
        self._updating = False

        self.x_spin, self.y_spin = _spin(-20000, 20000), _spin(-20000, 20000)
        self.w_spin, self.h_spin = _spin(1, 40000), _spin(1, 40000)
        self.keep_aspect = QCheckBox()
        self.keep_aspect.setChecked(True)
        self.flip_h = QCheckBox()
        self.flip_v = QCheckBox()
        self.flip_h.toggled.connect(self._on_flip_edited)
        self.flip_v.toggled.connect(self._on_flip_edited)
        for box in (self.x_spin, self.y_spin):
            box.valueChanged.connect(self._on_position_edited)
        self.w_spin.valueChanged.connect(lambda: self._on_size_edited("w"))
        self.h_spin.valueChanged.connect(lambda: self._on_size_edited("h"))

        self.crop_spins = {}
        for side in ("left", "top", "right", "bottom"):
            box = QSpinBox()
            box.setRange(0, 20000)
            box.setKeyboardTracking(False)
            box.valueChanged.connect(self._on_crop_edited)
            self.crop_spins[side] = box

        self.fit_btn = QPushButton()
        self.fit_btn.clicked.connect(self._on_fit)
        self.reset_crop_btn = QPushButton()
        self.reset_crop_btn.clicked.connect(self._on_reset_crop)

        geometry = QGridLayout()
        geometry.addWidget(QLabel("X"), 0, 0)
        geometry.addWidget(self.x_spin, 0, 1)
        geometry.addWidget(QLabel("Y"), 0, 2)
        geometry.addWidget(self.y_spin, 0, 3)
        geometry.addWidget(QLabel("W"), 1, 0)
        geometry.addWidget(self.w_spin, 1, 1)
        geometry.addWidget(QLabel("H"), 1, 2)
        geometry.addWidget(self.h_spin, 1, 3)
        geometry.addWidget(self.keep_aspect, 2, 0, 1, 4)
        geometry.addWidget(self.flip_h, 3, 0, 1, 2)
        geometry.addWidget(self.flip_v, 3, 2, 1, 2)

        crop = QGridLayout()
        self.crop_labels = {}
        for i, side in enumerate(("left", "right", "top", "bottom")):
            self.crop_labels[side] = QLabel()
            crop.addWidget(self.crop_labels[side], i // 2, (i % 2) * 2)
            crop.addWidget(self.crop_spins[side], i // 2, (i % 2) * 2 + 1)

        self.actions = QHBoxLayout()  # other panels can add their own buttons here
        self.actions.addWidget(self.fit_btn)
        self.actions.addWidget(self.reset_crop_btn)

        self.position_label = QLabel()
        self.crop_label = QLabel()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.position_label)
        layout.addLayout(geometry)
        layout.addWidget(self.crop_label)
        layout.addLayout(crop)
        layout.addLayout(self.actions)
        self.retranslate()
        self.set_layer(None)

    def retranslate(self) -> None:
        """Sets all texts in the current language."""
        self.position_label.setText(tr("<b>Position and size</b> (output pixels)"))
        self.keep_aspect.setText(tr("Lock aspect ratio"))
        self.flip_h.setText(tr("Mirror horizontally"))
        self.flip_v.setText(tr("Mirror vertically"))
        self.crop_label.setText(tr("<b>Crop</b> (source pixels)"))
        for side, text in (("left", tr("Left")), ("right", tr("Right")), ("top", tr("Top")), ("bottom", tr("Bottom"))):
            self.crop_labels[side].setText(text)
        self.fit_btn.setText(tr("Fit to canvas"))
        self.reset_crop_btn.setText(tr("Reset crop"))

    def set_layer(self, layer: Layer | None) -> None:
        """The layer to edit, or None (the fields are then disabled)."""
        self.layer = layer
        self.setEnabled(layer is not None)
        self.refresh()

    def refresh(self) -> None:
        """Updates the fields from the layer (skipping the field being edited)."""
        layer = self.layer
        if layer is None:
            return
        self._updating = True
        try:
            x, y, w, h = layer.display_rect()
            for box, value in ((self.x_spin, x), (self.y_spin, y), (self.w_spin, w), (self.h_spin, h)):
                if not box.hasFocus():
                    box.setValue(round(value))
            has_size = layer.source_size is not None
            self.w_spin.setEnabled(has_size)
            self.h_spin.setEnabled(has_size)
            for side, box in self.crop_spins.items():
                if layer.source_size:
                    box.setMaximum(max(0, (layer.source_size[0] if side in ("left", "right") else layer.source_size[1]) - 1))
                if not box.hasFocus():
                    box.setValue(getattr(layer.crop, side))
            self.flip_h.setChecked(layer.transform.flip_h)
            self.flip_v.setChecked(layer.transform.flip_v)
        finally:
            self._updating = False

    # --- handlers --------------------------------------------------------------

    def _on_position_edited(self) -> None:
        layer = self.layer
        if self._updating or layer is None:
            return
        layer.transform.x = self.x_spin.value()
        layer.transform.y = self.y_spin.value()

    def _on_size_edited(self, which: str) -> None:
        layer = self.layer
        if self._updating or layer is None or layer.source_size is None:
            return
        _, _, w, h = layer.display_rect()
        new_w, new_h = self.w_spin.value(), self.h_spin.value()
        if self.keep_aspect.isChecked() and w > 0 and h > 0:
            if which == "w":
                new_h = new_w * h / w
            else:
                new_w = new_h * w / h
        layer.set_display_size(new_w, new_h)
        self.refresh()

    def _on_crop_edited(self) -> None:
        layer = self.layer
        if self._updating or layer is None:
            return
        # keep the displayed scale: cropping removes content, it doesn't stretch what is left
        layer.crop = Crop(**{side: box.value() for side, box in self.crop_spins.items()})
        self.refresh()

    def _on_flip_edited(self) -> None:
        layer = self.layer
        if self._updating or layer is None:
            return
        layer.transform.flip_h = self.flip_h.isChecked()
        layer.transform.flip_v = self.flip_v.isChecked()

    def _on_fit(self) -> None:
        if self.layer is not None:
            self.layer.fit_to(self.engine.scene.output)
            self.refresh()

    def _on_reset_crop(self) -> None:
        if self.layer is not None:
            self.layer.crop = Crop()
            self.refresh()
