"""Preview of the composed output. Click to select a layer, drag to move it, drag a corner to resize it."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..engine import Engine
from ..model import Layer

HANDLE = 8  # handle size, widget pixels
MIN_SIZE = 4  # minimum layer size while resizing, output pixels


class PreviewWidget(QWidget):
    layer_selected = Signal(object)  # layer id or None
    layer_edited = Signal()  # geometry changed by mouse or keyboard

    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.image: QImage | None = None
        self.selected_id: str | None = None
        self._drag: dict | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 180)

    def set_image(self, image: QImage) -> None:
        self.image = image
        self.update()

    def set_selected(self, layer_id: str | None) -> None:
        self.selected_id = layer_id
        self.update()

    # --- coordinates -----------------------------------------------------------

    def _canvas_rect(self) -> QRectF:
        out = self.engine.scene.output
        area = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        scale = min(area.width() / out.width, area.height() / out.height)
        w, h = out.width * scale, out.height * scale
        return QRectF(area.x() + (area.width() - w) / 2, area.y() + (area.height() - h) / 2, w, h)

    def _scale(self) -> float:
        return self._canvas_rect().width() / self.engine.scene.output.width

    # When the output is mirrored the preview shows it mirrored too (what the camera sends),
    # so widget <-> canvas mappings flip the x axis.

    def _mirrored(self) -> bool:
        return self.engine.scene.output.mirror

    def _to_canvas(self, p: QPointF) -> QPointF:
        r = self._canvas_rect()
        s = self._scale()
        x = (p.x() - r.x()) / s
        if self._mirrored():
            x = self.engine.scene.output.width - x
        return QPointF(x, (p.y() - r.y()) / s)

    def _layer_widget_rect(self, layer: Layer) -> QRectF:
        x, y, w, h = layer.display_rect()
        if self._mirrored():
            x = self.engine.scene.output.width - x - w
        r = self._canvas_rect()
        s = self._scale()
        return QRectF(r.x() + x * s, r.y() + y * s, w * s, h * s)

    def _selected_layer(self) -> Layer | None:
        return self.engine.scene.layer_by_id(self.selected_id) if self.selected_id else None

    @staticmethod
    def _corners(rect: QRectF) -> list[QPointF]:
        return [rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()]

    def _handle_at(self, pos: QPointF) -> int | None:
        layer = self._selected_layer()
        if layer is None or layer.source_size is None:
            return None
        for i, corner in enumerate(self._corners(self._layer_widget_rect(layer))):
            if abs(pos.x() - corner.x()) <= HANDLE and abs(pos.y() - corner.y()) <= HANDLE:
                return i
        return None

    def _layer_at(self, pos: QPointF) -> Layer | None:
        for layer in reversed(self.engine.scene.layers):  # topmost first
            if layer.source_size and self._layer_widget_rect(layer).contains(pos):
                return layer
        return None

    # --- painting --------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(32, 32, 36))
        r = self._canvas_rect()
        if self.image is not None:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(r, self.image)
        else:
            p.fillRect(r, Qt.GlobalColor.black)

        layer = self._selected_layer()
        if layer is not None and layer.source_size is not None:
            lr = self._layer_widget_rect(layer)
            p.setPen(QPen(QColor(255, 80, 80), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(lr)
            p.setBrush(QColor(255, 80, 80))
            for c in self._corners(lr):
                p.drawRect(QRectF(c.x() - HANDLE / 2, c.y() - HANDLE / 2, HANDLE, HANDLE))

    # --- mouse -----------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        corner = self._handle_at(pos)
        if corner is not None:
            if self._mirrored():
                corner = (1, 0, 3, 2)[corner]  # widget corner -> canvas corner
            layer = self._selected_layer()
            x, y, w, h = layer.display_rect()
            anchor = [(x + w, y + h), (x, y + h), (x, y), (x + w, y)][corner]  # opposite corner
            self._drag = {"mode": "resize", "layer": layer, "corner": corner, "anchor": anchor, "aspect": w / h if h else 1.0}
            return

        layer = self._layer_at(pos)
        self.selected_id = layer.id if layer else None
        self.layer_selected.emit(self.selected_id)
        if layer is not None:
            self._drag = {"mode": "move", "layer": layer, "start": self._to_canvas(pos),
                          "origin": (layer.transform.x, layer.transform.y)}
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        if self._drag is None:
            self._update_cursor(pos)
            return

        layer: Layer = self._drag["layer"]
        cpos = self._to_canvas(pos)
        if self._drag["mode"] == "move":
            start: QPointF = self._drag["start"]
            ox, oy = self._drag["origin"]
            layer.transform.x = round(ox + cpos.x() - start.x())
            layer.transform.y = round(oy + cpos.y() - start.y())
        else:
            ax, ay = self._drag["anchor"]
            w = max(MIN_SIZE, abs(cpos.x() - ax))
            h = max(MIN_SIZE, abs(cpos.y() - ay))
            if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                aspect = self._drag["aspect"]
                if w / aspect > h:
                    h = w / aspect
                else:
                    w = h * aspect
            corner = self._drag["corner"]
            left = corner in (0, 3)
            top = corner in (0, 1)
            layer.transform.x = round(ax - w if left else ax)
            layer.transform.y = round(ay - h if top else ay)
            layer.set_display_size(round(w), round(h))
        self.layer_edited.emit()
        self.update()

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        self._drag = None

    def _update_cursor(self, pos: QPointF) -> None:
        corner = self._handle_at(pos)
        if corner is not None:
            shape = Qt.CursorShape.SizeFDiagCursor if corner in (0, 2) else Qt.CursorShape.SizeBDiagCursor
        elif self._layer_at(pos) is not None:
            shape = Qt.CursorShape.SizeAllCursor
        else:
            shape = Qt.CursorShape.ArrowCursor
        self.setCursor(shape)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Arrow keys nudge the selected layer (Shift: 10 px)."""
        layer = self._selected_layer()
        moves = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0), Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        if layer is None or event.key() not in moves:
            super().keyPressEvent(event)
            return
        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        dx, dy = moves[event.key()]
        if self._mirrored():
            dx = -dx  # move the way it looks in the preview
        layer.transform.x += dx * step
        layer.transform.y += dy * step
        self.layer_edited.emit()
        self.update()
