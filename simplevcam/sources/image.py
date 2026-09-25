from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..presets import read_image
from .base import Source


def load_bgra_or_bgr(path: str) -> np.ndarray | None:
    image = read_image(Path(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        return None
    if image.dtype != np.uint8:  # e.g. 16-bit PNG
        image = cv2.convertScaleAbs(image, alpha=255.0 / max(1, int(image.max())))
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return np.ascontiguousarray(image)


class ImageSource(Source):
    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def start(self) -> None:
        try:
            self._frame = load_bgra_or_bgr(self.path)
        except OSError:
            self._frame = None
        self.status = "" if self._frame is not None else f"immagine non trovata: {self.path}"
