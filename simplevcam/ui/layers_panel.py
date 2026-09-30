"""Layer list (top layer first, like OBS) and properties of the selected layer."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import (QAbstractItemView, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from ..engine import Engine
from ..i18n import tr
from ..model import Layer
from .geometry_editor import GeometryEditor


def type_label(source_type: str) -> str:
    return {"screen": tr("Screen"), "window": tr("Window"), "image": tr("Image"), "webcam": tr("Webcam")}[source_type]


def describe_source(layer: Layer) -> str:
    s = layer.source
    detail = {
        "screen": tr("monitor {index}", index=s.monitor),
        "window": f"{s.title or ''} ({s.exe or '?'})",
        "image": s.path or "",
        "webcam": s.name or f"#{s.index}",
    }[s.type]
    size = f" — {layer.source_size[0]}×{layer.source_size[1]}" if layer.source_size else ""
    return f"{type_label(s.type)}: {detail}{size}"


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

        self.list = _LayerList()
        self.list.currentItemChanged.connect(self._on_current_changed)
        self.list.reordered.connect(self._on_reordered)

        # texts are set in retranslate()
        self.add_btn = QPushButton()
        self.add_btn.clicked.connect(self.add_requested)
        self.remove_btn = QPushButton()
        self.remove_btn.clicked.connect(lambda: self._emit_for_selected(self.remove_requested))
        self.up_btn = QPushButton("▲")
        self.up_btn.clicked.connect(lambda: self._emit_for_selected(self.move_requested, 1))
        self.down_btn = QPushButton("▼")
        self.down_btn.clicked.connect(lambda: self._emit_for_selected(self.move_requested, -1))
        self.mask_btn = QPushButton()
        self.mask_btn.clicked.connect(lambda: self._emit_for_selected(self.mask_requested))
        for b in (self.up_btn, self.down_btn):
            b.setFixedWidth(32)

        buttons = QHBoxLayout()
        for b in (self.add_btn, self.remove_btn, self.up_btn, self.down_btn, self.mask_btn):
            buttons.addWidget(b)

        # properties
        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._on_name_edited)
        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #d04040")
        self.geometry = GeometryEditor(engine)  # position, size, mirroring, crop

        self.name_label = QLabel()
        form = QFormLayout()
        form.addRow(self.name_label, self.name_edit)
        form.addRow(self.source_label)
        form.addRow(self.status_label)
        form.addRow(self.geometry)

        self.props = QGroupBox()
        self.props.setLayout(form)

        self.header = QLabel()
        layout = QVBoxLayout(self)
        layout.addWidget(self.header)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)
        layout.addWidget(self.props)
        self.retranslate()
        self._sync_enabled()

    def retranslate(self) -> None:
        """Sets all texts in the current language."""
        self.header.setText(tr("<b>Layers</b> — the one at the top of the list is in front.<br>"
                               "Drag a layer up or down to change the order."))
        self.add_btn.setText(tr("+ Add"))
        self.remove_btn.setText(tr("− Remove"))
        self.up_btn.setToolTip(tr("Move up"))
        self.down_btn.setToolTip(tr("Move down"))
        self.mask_btn.setText(tr("Mask…"))
        self.props.setTitle(tr("Properties"))
        self.name_label.setText(tr("Name"))
        self.geometry.retranslate()
        self.rebuild()  # list tooltips and the source description

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
        self.geometry.set_layer(layer)
        if layer is None:
            return
        if not self.name_edit.hasFocus():
            self.name_edit.setText(layer.name)
        self.source_label.setText(describe_source(layer))
        self.status_label.setText(self.engine.source_status(layer.id))
        self.status_label.setVisible(bool(self.status_label.text()))
        self.mask_btn.setText(tr("Mask…") + (" ●" if layer.mask is not None else ""))

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
