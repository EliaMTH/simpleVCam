"""Layer list (top layer first, like OBS) and properties of the selected layer."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import (QAbstractItemView, QAbstractSpinBox, QCheckBox,QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from ..engine import Engine
from ..model import Crop, Layer

TYPE_LABELS = {"screen": "Schermo", "window": "Finestra", "image": "Immagine", "webcam": "Webcam"}


def describe_source(layer: Layer) -> str:
    s = layer.source
    detail = {
        "screen": f"monitor {s.monitor}",
        "window": f"{s.title or ''} ({s.exe or '?'})",
        "image": s.path or "",
        "webcam": s.name or f"#{s.index}",
    }[s.type]
    size = f" — {layer.source_size[0]}×{layer.source_size[1]}" if layer.source_size else ""
    return f"{TYPE_LABELS[s.type]}: {detail}{size}"


class _LayerList(QListWidget):
    """List whose items can be dragged to change the layer order."""

    reordered = Signal()

    def __init__(self):
        super().__init__()
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)

    def dropEvent(self, event: QDropEvent) -> None:
        super().dropEvent(event)
        self.reordered.emit()


def _spin(minimum: float, maximum: float) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setDecimals(0)
    box.setKeyboardTracking(False)
    box.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    return box


class LayersPanel(QWidget):
    selection_changed = Signal(object)  # layer id or None
    add_requested = Signal()
    remove_requested = Signal(str)
    move_requested = Signal(str, int)
    order_changed = Signal(list)  # layer ids, bottom to top
    mask_requested = Signal(str)

    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._updating = False

        self.list = _LayerList()
        self.list.currentItemChanged.connect(self._on_current_changed)
        self.list.reordered.connect(self._on_reordered)

        add = QPushButton("+ Aggiungi")
        add.clicked.connect(self.add_requested)
        self.remove_btn = QPushButton("− Rimuovi")
        self.remove_btn.clicked.connect(lambda: self._emit_for_selected(self.remove_requested))
        self.up_btn = QPushButton("▲")
        self.up_btn.setToolTip("Porta su")
        self.up_btn.clicked.connect(lambda: self._emit_for_selected(self.move_requested, 1))
        self.down_btn = QPushButton("▼")
        self.down_btn.setToolTip("Porta giù")
        self.down_btn.clicked.connect(lambda: self._emit_for_selected(self.move_requested, -1))
        self.mask_btn = QPushButton("Mask…")
        self.mask_btn.clicked.connect(lambda: self._emit_for_selected(self.mask_requested))
        for b in (self.up_btn, self.down_btn):
            b.setFixedWidth(32)

        buttons = QHBoxLayout()
        for b in (add, self.remove_btn, self.up_btn, self.down_btn, self.mask_btn):
            buttons.addWidget(b)

        # properties
        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._on_name_edited)
        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #d04040")

        self.x_spin, self.y_spin = _spin(-20000, 20000), _spin(-20000, 20000)
        self.w_spin, self.h_spin = _spin(1, 40000), _spin(1, 40000)
        self.keep_aspect = QCheckBox("Blocca proporzioni")
        self.keep_aspect.setChecked(True)
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

        fit_btn = QPushButton("Adatta al canvas")
        fit_btn.clicked.connect(self._on_fit)
        reset_crop_btn = QPushButton("Reset crop")
        reset_crop_btn.clicked.connect(self._on_reset_crop)

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

        crop = QGridLayout()
        for i, (side, label) in enumerate((("left", "Sinistra"), ("right", "Destra"), ("top", "Sopra"), ("bottom", "Sotto"))):
            crop.addWidget(QLabel(label), i // 2, (i % 2) * 2)
            crop.addWidget(self.crop_spins[side], i // 2, (i % 2) * 2 + 1)

        form = QFormLayout()
        form.addRow("Nome", self.name_edit)
        form.addRow(self.source_label)
        form.addRow(self.status_label)
        form.addRow(QLabel("<b>Posizione e dimensione</b> (pixel di output)"))
        form.addRow(geometry)
        form.addRow(QLabel("<b>Crop</b> (pixel della sorgente)"))
        form.addRow(crop)
        actions = QHBoxLayout()
        actions.addWidget(fit_btn)
        actions.addWidget(reset_crop_btn)
        form.addRow(actions)

        self.props = QGroupBox("Proprietà")
        self.props.setLayout(form)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Layer</b> — quello in cima alla lista è in primo piano.<br>"
                                "Trascina un layer su o giù per cambiare l'ordine."))
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)
        layout.addWidget(self.props)
        self._sync_enabled()

    # --- public ----------------------------------------------------------------

    def selected_layer(self) -> Layer | None:
        item = self.list.currentItem()
        return self.engine.scene.layer_by_id(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def rebuild(self, select_id: str | None = None) -> None:
        """Rebuilds the list from the scene, keeping (or setting) the selection."""
        if select_id is None:
            current = self.selected_layer()
            select_id = current.id if current else None
        self.list.blockSignals(True)
        self.list.clear()
        for layer in reversed(self.engine.scene.layers):
            item = QListWidgetItem(layer.name)
            item.setData(Qt.ItemDataRole.UserRole, layer.id)
            item.setToolTip(describe_source(layer))
            self.list.addItem(item)
            if layer.id == select_id:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        self._sync_enabled()
        self.refresh()
        self.selection_changed.emit(select_id if self.selected_layer() else None)

    def select(self, layer_id: str | None) -> None:
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == layer_id:
                self.list.setCurrentRow(i)
                return
        self.list.setCurrentItem(None)

    def refresh(self) -> None:
        """Updates the property fields from the selected layer (skipping the field being edited)."""
        layer = self.selected_layer()
        if layer is None:
            return
        self._updating = True
        try:
            if not self.name_edit.hasFocus():
                self.name_edit.setText(layer.name)
            self.source_label.setText(describe_source(layer))
            self.status_label.setText(self.engine.source_status(layer.id))
            self.status_label.setVisible(bool(self.status_label.text()))
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
            self.mask_btn.setText("Mask… ●" if layer.mask is not None else "Mask…")
        finally:
            self._updating = False

    # --- handlers --------------------------------------------------------------

    def _emit_for_selected(self, signal, *args) -> None:
        layer = self.selected_layer()
        if layer is not None:
            signal.emit(layer.id, *args)

    def _sync_enabled(self) -> None:
        has = self.selected_layer() is not None
        for w in (self.remove_btn, self.up_btn, self.down_btn, self.mask_btn, self.props):
            w.setEnabled(has)

    def _on_current_changed(self, *_):
        self._sync_enabled()
        self.refresh()
        layer = self.selected_layer()
        self.selection_changed.emit(layer.id if layer else None)

    def _on_reordered(self) -> None:
        ids = [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]
        self.order_changed.emit(list(reversed(ids)))  # the list shows the top layer first

    def _on_name_edited(self) -> None:
        layer = self.selected_layer()
        name = self.name_edit.text().strip()
        if layer is not None and name and name != layer.name:
            layer.name = name
            self.list.currentItem().setText(name)

    def _on_position_edited(self) -> None:
        layer = self.selected_layer()
        if self._updating or layer is None:
            return
        layer.transform.x = self.x_spin.value()
        layer.transform.y = self.y_spin.value()

    def _on_size_edited(self, which: str) -> None:
        layer = self.selected_layer()
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
        layer = self.selected_layer()
        if self._updating or layer is None:
            return
        # keep the displayed scale: cropping removes content, it doesn't stretch what is left
        layer.crop = Crop(**{side: box.value() for side, box in self.crop_spins.items()})
        self.refresh()

    def _on_fit(self) -> None:
        layer = self.selected_layer()
        if layer is not None:
            layer.fit_to(self.engine.scene.output)
            self.refresh()

    def _on_reset_crop(self) -> None:
        layer = self.selected_layer()
        if layer is not None:
            layer.crop = Crop()
            self.refresh()
