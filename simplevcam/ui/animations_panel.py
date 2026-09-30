"""Animations panel: nine buttons that play the soundboard animations over the output, and their settings."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QToolButton, QVBoxLayout, QWidget)

from ..animations import Slot, scan_slots
from ..engine import Engine
from ..i18n import tr
from ..model import ANIMATION_PLAYS, ANIMATION_SLOTS
from .geometry_editor import GeometryEditor

ICON_SIZE = 56
# border: normal, playing, being positioned (red like the selection in the preview)
BORDERS = {"idle": "#1c1d21", "playing": "#3cb96a", "editing": "#ff5050"}
TEXT, EMPTY_TEXT = "#e6e6e9", "#7d7d84"
SLOT_STYLE = ("QToolButton {{ color: {text}; background: #34373e; border: 2px solid {border}; border-radius: 6px; "
              "padding: 2px; }}"
              "QToolButton:hover {{ background: #40444c; }}"
              "QToolButton:pressed {{ background: #2a2c32; }}")


def magic_wand_icon(size: int = 64) -> QIcon:
    """Icon of the button that shows the panel: a magic wand (drawn, so it doesn't depend on emoji fonts)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 64, size / 64)  # drawn on a 64x64 grid
    stick = QPen(QColor(165, 168, 180), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(stick)
    p.drawLine(QPointF(8, 56), QPointF(31, 33))
    stick.setColor(QColor(255, 255, 255))
    p.setPen(stick)
    p.drawLine(QPointF(31, 33), QPointF(36, 28))  # white tip
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 200, 60))
    for cx, cy, r in ((46, 18, 14), (57, 39, 6), (26, 8, 6)):  # sparkles: four points joined by curves
        center = QPointF(cx, cy)
        star = QPainterPath(QPointF(cx, cy - r))
        for x, y in ((cx + r, cy), (cx, cy + r), (cx - r, cy), (cx, cy - r)):
            star.quadTo(center, QPointF(x, y))
        p.drawPath(star)
    p.end()
    return QIcon(pixmap)


class AnimationsPanel(QWidget):
    editing_changed = Signal(object)  # id of the placement being positioned, or None

    def __init__(self, engine: Engine, folder: Path, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.folder = folder
        self.slots: dict[int, Slot] = {}
        self.editing: int | None = None  # slot being positioned
        self._scanned = False

        self.header = QLabel()
        self.header.setWordWrap(True)
        self.buttons: dict[int, QToolButton] = {}
        self._states: dict[int, tuple[str, bool]] = {}  # index -> (state, empty) last shown
        grid = QGridLayout()
        for index in ANIMATION_SLOTS:
            button = QToolButton()
            button.setText(str(index))
            button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
            button.setFixedSize(ICON_SIZE + 24, ICON_SIZE + 30)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.clicked.connect(lambda _=False, i=index: self._on_slot_clicked(i))
            self.buttons[index] = button
            grid.addWidget(button, (index - 1) // 3, (index - 1) % 3)

        # texts are set in retranslate()
        self.folder_btn = QPushButton()
        self.folder_btn.clicked.connect(lambda: self._open_folder(self.folder))
        self.reload_btn = QPushButton()
        self.reload_btn.clicked.connect(self.reload)
        self.position_btn = QPushButton()
        self.position_btn.setCheckable(True)
        self.position_btn.toggled.connect(self._on_position_toggled)
        tools = QHBoxLayout()
        for b in (self.folder_btn, self.reload_btn, self.position_btn):
            tools.addWidget(b)

        # settings of the slot chosen with a click: how many times it plays, and the controls of a layer
        self.position_help = QLabel()
        self.position_help.setWordWrap(True)
        self.plays_label = QLabel()
        self.plays_combo = QComboBox()
        self.plays_combo.setEnabled(False)
        self.plays_combo.currentIndexChanged.connect(self._on_plays_changed)
        plays = QHBoxLayout()
        plays.addWidget(self.plays_label)
        plays.addWidget(self.plays_combo)
        plays.addStretch(1)
        self.geometry = GeometryEditor(engine)
        self.native_btn = QPushButton()
        self.native_btn.clicked.connect(self._on_native)
        self.geometry.actions.addWidget(self.native_btn)
        self.position_box = QGroupBox()
        box = QVBoxLayout(self.position_box)
        box.addWidget(self.position_help)
        box.addLayout(plays)
        box.addWidget(self.geometry)
        self.position_box.setVisible(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.header)
        layout.addLayout(grid)
        layout.addLayout(tools)
        layout.addWidget(self.position_box)
        layout.addStretch(1)
        self.retranslate()

    def retranslate(self) -> None:
        """Sets all texts in the current language."""
        self.header.setText(tr("<b>Animations</b> — click a button to play its animation."))
        self.folder_btn.setText(tr("Open folder"))
        self.folder_btn.setToolTip(str(self.folder))
        self.reload_btn.setText(tr("Reload"))
        self.reload_btn.setToolTip(tr("Reads the slot folders again, after changing their files"))
        self.position_btn.setText(tr("✎ Adjust"))
        self.position_btn.setToolTip(tr("How many times an animation plays, where it appears, its size, crop and "
                                        "mirroring; presets save them"))
        self.position_box.setTitle(tr("Settings"))
        self.plays_label.setText(tr("Play:"))
        self.plays_combo.setToolTip(tr("How many times in a row the animation plays when you click it"))
        self._fill_plays()
        self.native_btn.setText(tr("1:1 centered"))
        self.native_btn.setToolTip(tr("The animation at its own size, in the center"))
        self.geometry.retranslate()
        self._update_position_help()
        self._update_buttons()

    # --- public ----------------------------------------------------------------

    def reload(self) -> None:
        """Reads the slot folders again (the user may have changed their files)."""
        self._scanned = True
        try:
            slots = scan_slots(self.folder)
        except OSError as e:
            QMessageBox.warning(self, "simpleVCam", tr("Cannot read the animations folder:\n{error}", error=e))
            slots = []
        self.slots = {slot.index: slot for slot in slots}
        self._update_buttons()
        if self.editing is not None:
            self._edit(self.editing)  # its file may have changed

    def refresh(self) -> None:
        """Shows which animations are playing or being positioned, and updates the positioning fields."""
        for index, button in self.buttons.items():
            if index == self.editing:
                state = "editing"
            elif self.engine.animation_playing(index):
                state = "playing"
            else:
                state = "idle"
            slot = self.slots.get(index)
            empty = slot is None or slot.path is None
            if self._states.get(index) != (state, empty):  # called periodically: avoid re-applying style sheets
                self._states[index] = (state, empty)
                button.setStyleSheet(SLOT_STYLE.format(border=BORDERS[state], text=EMPTY_TEXT if empty else TEXT))
                button.setToolTip(self._tooltip(index))  # a playback may have ended with an error
        self.geometry.refresh()

    def scene_changed(self) -> None:
        """A preset was loaded: go on positioning the same slot, with the placement of the new preset."""
        if self.editing is not None:
            self._edit(self.editing)

    def stop_positioning(self) -> None:
        self.position_btn.setChecked(False)

    # --- internals -------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._scanned:  # the folders are read the first time the panel is shown
            self.reload()

    def _update_buttons(self) -> None:
        for index, button in self.buttons.items():
            slot = self.slots.get(index)
            icon = QPixmap(str(slot.icon)) if slot is not None and slot.icon is not None else QPixmap()
            button.setIcon(QIcon(icon) if not icon.isNull() else QIcon())
            button.setText(f"{index} ⚠" if slot is not None and slot.error else str(index))
            button.setToolTip(self._tooltip(index))
        self.refresh()

    def _tooltip(self, index: int) -> str:
        slot = self.slots.get(index)
        if slot is None:
            return ""
        if slot.path is None:
            return tr("Empty: put an animation (WebP, APNG or GIF) and icon.png in\n{folder}\n"
                      "Click to open the folder.", folder=slot.folder)
        if slot.error:
            return f"{slot.path.name}\n{slot.error}"
        tip = f"{slot.path.name} — {slot.size[0]}×{slot.size[1]}"
        error = self.engine.animation_error(index)
        return f"{tip}\n{error}" if error else tip

    def _on_slot_clicked(self, index: int) -> None:
        slot = self.slots.get(index)
        if slot is None:
            return
        if slot.path is None:
            self._open_folder(slot.folder)
        elif slot.error:
            QMessageBox.warning(self, "simpleVCam", f"{slot.path}\n\n{slot.error}")
        elif self.position_btn.isChecked():
            self._edit(index)
        else:
            self.engine.play_animation(slot)
            self.refresh()

    def _on_position_toggled(self, on: bool) -> None:
        self.position_box.setVisible(on)
        if not on:
            self._edit(None)
        self._update_position_help()

    def _edit(self, index: int | None) -> None:
        """Starts positioning slot `index`; None stops."""
        slot = self.slots.get(index) if index is not None else None
        if slot is not None and not slot.playable:
            slot = None
        # the placement first, so the loop starts in the right place
        layer = self.engine.animation_layer(slot) if slot is not None else None
        self.engine.edit_animation(slot)
        self.editing = slot.index if slot is not None else None
        self.geometry.set_layer(layer)
        self.native_btn.setEnabled(layer is not None)
        self.plays_combo.setEnabled(layer is not None)
        self._show_plays(layer.plays if layer is not None else 1)
        self._update_position_help()
        self.refresh()
        self.editing_changed.emit(layer.id if layer is not None else None)

    def _on_native(self) -> None:
        if self.geometry.layer is not None:
            self.geometry.layer.center_native(self.engine.scene.output)
            self.geometry.refresh()

    def _fill_plays(self) -> None:
        """The choices of how many times an animation plays, in the current language."""
        current = self.plays_combo.currentData() or 1
        self.plays_combo.blockSignals(True)
        self.plays_combo.clear()
        for n in ANIMATION_PLAYS:
            self.plays_combo.addItem(tr("once") if n == 1 else tr("{count} times", count=n), n)
        self.plays_combo.blockSignals(False)
        self._show_plays(current)

    def _show_plays(self, plays: int) -> None:
        self.plays_combo.blockSignals(True)
        self.plays_combo.setCurrentIndex(self.plays_combo.findData(plays))
        self.plays_combo.blockSignals(False)

    def _on_plays_changed(self) -> None:
        if self.geometry.layer is not None:  # the placement of the slot being adjusted
            self.geometry.layer.plays = self.plays_combo.currentData()

    def _update_position_help(self) -> None:
        if self.editing is None:
            text = tr("Click an animation to adjust it. Meanwhile it loops in the preview only: "
                      "the camera doesn't show it.")
        else:
            text = tr("Animation {index}: drag it in the preview, or use the fields below. "
                      "The camera doesn't show it until you play it.", index=self.editing)
        self.position_help.setText(text)

    def _open_folder(self, folder: Path) -> None:
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # opening it will fail visibly
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
