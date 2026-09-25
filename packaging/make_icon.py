"""Draws the app icon and writes simplevcam/assets/simplevcam.ico (multi-size) and simplevcam.png.

The generated files are committed; run this only to change the icon:

    .venv\\Scripts\\python packaging\\make_icon.py
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen

SIZES = [16, 24, 32, 48, 64, 128, 256]
ASSETS = Path(__file__).resolve().parents[1] / "simplevcam" / "assets"


def draw(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 256, size / 256)  # draw on a 256x256 grid

    # background tile
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(40, 44, 54))
    p.drawRoundedRect(QRectF(8, 8, 240, 240), 48, 48)

    # stacked layers behind the camera
    for i, color in enumerate((QColor(46, 139, 87), QColor(58, 120, 215))):
        p.setBrush(color)
        p.drawRoundedRect(QRectF(40 + i * 18, 52 + i * 18, 150, 100), 18, 18)

    # camera body and lens
    p.setBrush(QColor(236, 238, 242))
    p.drawRoundedRect(QRectF(76, 104, 140, 100), 20, 20)
    p.drawRoundedRect(QRectF(118, 88, 56, 24), 8, 8)
    p.setBrush(QColor(40, 44, 54))
    p.drawEllipse(QRectF(116, 124, 60, 60))
    p.setPen(QPen(QColor(58, 120, 215), 10))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(128, 136, 36, 36))

    # "on air" dot
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(210, 60, 50))
    p.drawEllipse(QRectF(190, 114, 16, 16))
    p.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def write_ico(path: Path, images: list[QImage]) -> None:
    """ICO with PNG-compressed entries (supported since Windows Vista)."""
    entries = [png_bytes(img) for img in images]
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory = b""
    for img, data in zip(images, entries):
        w = img.width() if img.width() < 256 else 0  # 0 means 256
        directory += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.write_bytes(header + directory + b"".join(entries))


def main() -> int:
    QGuiApplication(sys.argv)
    ASSETS.mkdir(parents=True, exist_ok=True)
    images = [draw(s) for s in SIZES]
    write_ico(ASSETS / "simplevcam.ico", images)
    images[-1].save(str(ASSETS / "simplevcam.png"))
    print("written", ASSETS / "simplevcam.ico")
    return 0


if __name__ == "__main__":
    sys.exit(main())
