"""Editor of a layer's binary mask (white = visible, black = hidden), drawn over a snapshot of the source."""
from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QKeySequence, QMouseEvent, QPainter, QPen, QShortcut, QWheelEvent
from PySide6.QtWidgets import (QButtonGroup, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton,
                               QRadioButton, QScrollArea, QSlider, QVBoxLayout, QWidget)

from ..model import Layer

MAX_UNDO = 20
OVERLAY_ALPHA = 130  # red tint over hidden areas


def to_qimage_bgr(frame: np.ndarray) -> QImage:
    """QImage (owning its data) from a BGR/BGRA frame."""
    if frame.ndim == 3 and frame.shape[2] == 3:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
    frame = np.ascontiguousarray(frame)
    h, w = frame.shape[:2]
    return QImage(frame.data, w, h, w * 4, QImage.Format.Format_RGB32).copy()


class MaskCanvas(QWidget):
    """Shows the source with the mask overlay and turns mouse input into drawing on the mask."""

    def __init__(self, editor: MaskEditorDialog):
        super().__init__()
        self.editor = editor
        self.zoom = 1.0
        self.hover: QPointF | None = None
        self.shape_start: QPoint | None = None
        self.shape_end: QPoint | None = None
        self.last_point: QPoint | None = None
        self.value = 255
        self.overlay: QImage | None = None
        self.setMouseTracking(True)
        self.rebuild_overlay()
        self.set_zoom(1.0)

    def set_zoom(self, zoom: float) -> None:
        self.zoom = max(0.05, min(8.0, zoom))
        h, w = self.editor.mask.shape
        self.setFixedSize(max(1, round(w * self.zoom)), max(1, round(h * self.zoom)))
        self.update()

    def rebuild_overlay(self) -> None:
        mask = self.editor.mask
        h, w = mask.shape
        overlay = np.zeros((h, w, 4), np.uint8)  # premultiplied BGRA
        hidden = mask == 0
        overlay[hidden, 2] = OVERLAY_ALPHA
        overlay[hidden, 3] = OVERLAY_ALPHA
        self.overlay = QImage(overlay.data, w, h, w * 4, QImage.Format.Format_ARGB32_Premultiplied).copy()
        self.update()

    def _image_point(self, pos: QPointF) -> QPoint:
        return QPoint(int(pos.x() / self.zoom), int(pos.y() / self.zoom))

    def _shape_end(self, event: QMouseEvent) -> QPoint:
        """End point of the rectangle/ellipse being dragged; with Ctrl the sides are equal (square/circle)."""
        pt = self._image_point(event.position())
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return pt
        dx, dy = pt.x() - self.shape_start.x(), pt.y() - self.shape_start.y()
        side = max(abs(dx), abs(dy))
        return QPoint(self.shape_start.x() + (side if dx >= 0 else -side), self.shape_start.y() + (side if dy >= 0 else -side))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.scale(self.zoom, self.zoom)
        p.drawImage(0, 0, self.editor.background)
        p.drawImage(0, 0, self.overlay)

        pen = QPen(QColor(255, 255, 255), 0, Qt.PenStyle.DashLine)  # cosmetic: 1 px at any zoom
        c = self.editor.layer.crop
        h, w = self.editor.mask.shape
        if any(c.as_tuple()):
            p.setPen(QPen(QColor(255, 210, 0), 0, Qt.PenStyle.DashLine))
            p.drawRect(QRectF(c.left, c.top, w - c.left - c.right, h - c.top - c.bottom))

        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self.shape_start is not None and self.shape_end is not None:
            rect = QRectF(QPointF(self.shape_start), QPointF(self.shape_end)).normalized()
            if self.editor.tool == "ellipse":
                p.drawEllipse(rect)
            else:
                p.drawRect(rect)
        elif self.editor.tool == "brush" and self.hover is not None:
            r = self.editor.brush_size / 2
            p.drawEllipse(QPointF(self.hover.x() / self.zoom, self.hover.y() / self.zoom), r, r)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return
        primary = self.editor.paint_value
        self.value = primary if event.button() == Qt.MouseButton.LeftButton else 255 - primary
        pt = self._image_point(event.position())
        self.editor.push_undo()
        if self.editor.tool == "brush":
            self.last_point = pt
            self._stroke(pt)
        else:
            self.shape_start = self.shape_end = pt
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self.hover = event.position()
        pt = self._image_point(event.position())
        if self.last_point is not None:
            self._stroke(pt)
        elif self.shape_start is not None:
            self.shape_end = self._shape_end(event)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.shape_start is not None and self.shape_end is not None:
            self.shape_end = self._shape_end(event)
            x0, y0 = self.shape_start.x(), self.shape_start.y()
            x1, y1 = self.shape_end.x(), self.shape_end.y()
            mask = self.editor.mask
            if self.editor.tool == "rect":
                cv2.rectangle(mask, (x0, y0), (x1, y1), self.value, thickness=-1, lineType=cv2.LINE_8)
            else:
                center = ((x0 + x1) // 2, (y0 + y1) // 2)
                axes = (abs(x1 - x0) // 2, abs(y1 - y0) // 2)
                cv2.ellipse(mask, center, axes, 0, 0, 360, self.value, thickness=-1, lineType=cv2.LINE_8)
            self.rebuild_overlay()
        self.shape_start = self.shape_end = self.last_point = None
        self.update()

    def leaveEvent(self, _event) -> None:
        self.hover = None
        self.update()

    def _stroke(self, pt: QPoint) -> None:
        size = self.editor.brush_size
        mask = self.editor.mask
        p0 = (self.last_point.x(), self.last_point.y())
        p1 = (pt.x(), pt.y())
        cv2.line(mask, p0, p1, self.value, thickness=size, lineType=cv2.LINE_8)
        cv2.circle(mask, p1, size // 2, self.value, thickness=-1, lineType=cv2.LINE_8)
        self.last_point = pt
        self.rebuild_overlay()


class _ScrollArea(QScrollArea):
    """Ctrl + wheel zooms instead of scrolling."""

    def __init__(self, canvas: MaskCanvas):
        super().__init__()
        self.canvas = canvas
        self.setWidget(canvas)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("QScrollArea { background: #202024; }")

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.canvas.set_zoom(self.canvas.zoom * factor)
        else:
            super().wheelEvent(event)


class MaskEditorDialog(QDialog):
    def __init__(self, layer: Layer, frame: np.ndarray | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Mask — {layer.name}")
        self.layer = layer
        self.removed = False

        if frame is not None:
            h, w = frame.shape[:2]
            self.background = to_qimage_bgr(frame)
        else:
            w, h = layer.source_size or (layer.mask.shape[1], layer.mask.shape[0])
            self.background = QImage(w, h, QImage.Format.Format_RGB32)
            self.background.fill(QColor(60, 60, 60))

        if layer.mask is None:
            self.mask = np.full((h, w), 255, np.uint8)
        elif layer.mask.shape != (h, w):
            # the source changed size: adapt the mask, like the compositor does
            self.mask = cv2.resize(layer.mask, (w, h), interpolation=cv2.INTER_NEAREST)
        else:
            self.mask = layer.mask.copy()
        self.undo_stack: list[np.ndarray] = []
        self.tool = "brush"
        self.paint_value = 0  # left button hides: masks usually cut something away
        self.brush_size = max(4, min(w, h) // 20)

        self.canvas = MaskCanvas(self)
        self.scroll = _ScrollArea(self.canvas)

        # tools
        tools = QButtonGroup(self)
        tool_row = QHBoxLayout()
        tool_row.addWidget(QLabel("Strumento:"))
        for key, label in (("brush", "Pennello"), ("rect", "Rettangolo"), ("ellipse", "Ellisse")):
            b = QRadioButton(label)
            b.setChecked(key == self.tool)
            b.toggled.connect(lambda on, k=key: on and self._set_tool(k))
            tools.addButton(b)
            tool_row.addWidget(b)
        tool_row.addSpacing(20)

        modes = QButtonGroup(self)
        tool_row.addWidget(QLabel("Tasto sinistro:"))
        for value, label in ((0, "nasconde"), (255, "rende visibile")):
            b = QRadioButton(label)
            b.setChecked(value == self.paint_value)
            b.toggled.connect(lambda on, v=value: on and self._set_paint_value(v))
            modes.addButton(b)
            tool_row.addWidget(b)
        tool_row.addSpacing(20)

        self.size_label = QLabel()
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(1, max(2, min(w, h) // 2))
        self.size_slider.setValue(self.brush_size)
        self.size_slider.valueChanged.connect(self._set_brush_size)
        self.size_slider.setFixedWidth(160)
        tool_row.addWidget(QLabel("Pennello:"))
        tool_row.addWidget(self.size_slider)
        tool_row.addWidget(self.size_label)
        tool_row.addStretch(1)
        self._set_brush_size(self.brush_size)

        # actions
        action_row = QHBoxLayout()
        for label, slot in (("Mostra tutto", self._fill_all), ("Nascondi tutto", self._clear_all), ("Inverti", self._invert),
                            ("Annulla (Ctrl+Z)", self.undo)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            action_row.addWidget(b)
        action_row.addSpacing(20)
        for label, slot in (("Adatta", self.fit_zoom), ("100%", lambda: self.canvas.set_zoom(1.0))):
            b = QPushButton(label)
            b.clicked.connect(slot)
            action_row.addWidget(b)
        action_row.addStretch(1)

        # instructions, updated with the selected tool and mode
        self.help = QLabel()
        self.help.setWordWrap(True)
        self.help.setTextFormat(Qt.TextFormat.RichText)
        self.help.setStyleSheet("QLabel { background: #2c313c; border: 1px solid #454c5a; border-radius: 4px; padding: 8px; }")

        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self.undo)

        remove = QPushButton("Rimuovi mask")
        remove.clicked.connect(self._remove)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(remove)
        bottom.addStretch(1)
        bottom.addWidget(buttons)

        layout = QVBoxLayout(self)
        layout.addLayout(tool_row)
        layout.addLayout(action_row)
        layout.addWidget(self.help)
        layout.addWidget(self.scroll, 1)
        layout.addLayout(bottom)
        self.resize(1200, 860)
        self._update_help()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.fit_zoom()

    def result_mask(self) -> np.ndarray | None:
        """The edited mask, or None if the user removed it."""
        return None if self.removed else self.mask

    # --- editing ---------------------------------------------------------------

    def push_undo(self) -> None:
        self.undo_stack.append(self.mask.copy())
        del self.undo_stack[:-MAX_UNDO]

    def undo(self) -> None:
        if self.undo_stack:
            self.mask[...] = self.undo_stack.pop()
            self.canvas.rebuild_overlay()

    def _set_tool(self, tool: str) -> None:
        self.tool = tool
        self.canvas.update()
        self._update_help()

    def _set_paint_value(self, value: int) -> None:
        self.paint_value = value
        self._update_help()

    def _update_help(self) -> None:
        show = "rende <b>VISIBILE</b> (toglie il rosso)"
        hide = "<b>NASCONDE</b> (colora di rosso)"
        left, right = (show, hide) if self.paint_value == 255 else (hide, show)
        tool = {
            "brush": "<b>Pennello:</b> tieni premuto il tasto e trascina per dipingere; "
                     "la dimensione si regola con il cursore «Pennello».",
            "rect": "<b>Rettangolo:</b> trascina da un angolo a quello opposto; "
                    "quando rilasci il tasto, il rettangolo viene riempito. Tieni premuto <b>Ctrl</b> per un quadrato.",
            "ellipse": "<b>Ellisse:</b> trascina per disegnare il riquadro che contiene l'ellisse; "
                       "quando rilasci il tasto, l'ellisse viene riempita. Tieni premuto <b>Ctrl</b> per un cerchio.",
        }[self.tool]
        self.help.setText(
            "<b>Come leggere l'immagine:</b> le zone <span style='color:#ff6b6b'><b>rosse</b></span> "
            "saranno <b>nascoste</b> nella camera, tutto il resto sarà visibile.<br>"
            f"<b>Tasto sinistro del mouse:</b> {left}. &nbsp; <b>Tasto destro:</b> {right}.<br>"
            f"{tool}<br>"
            "<b>Zoom:</b> Ctrl + rotella del mouse, oppure «Adatta» e «100%». &nbsp; <b>Annulla:</b> Ctrl+Z. &nbsp; "
            "Il riquadro giallo tratteggiato, se presente, è il crop del layer."
        )

    def _set_brush_size(self, size: int) -> None:
        self.brush_size = size
        self.size_label.setText(f"{size} px")

    def _apply(self, operation) -> None:
        self.push_undo()
        operation()
        self.canvas.rebuild_overlay()

    def _fill_all(self) -> None:
        self._apply(lambda: self.mask.fill(255))

    def _clear_all(self) -> None:
        self._apply(lambda: self.mask.fill(0))

    def _invert(self) -> None:
        self._apply(lambda: np.subtract(255, self.mask, out=self.mask))

    def _remove(self) -> None:
        self.removed = True
        self.accept()

    def fit_zoom(self) -> None:
        h, w = self.mask.shape
        viewport = self.scroll.viewport().size()
        self.canvas.set_zoom(min((viewport.width() - 4) / w, (viewport.height() - 4) / h))
