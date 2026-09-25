from __future__ import annotations

import threading

import cv2

from ..i18n import tr
from .base import Source
from .winutil import list_webcams


class WebcamSource(Source):
    """Reads a physical camera through DirectShow on a background thread."""

    def __init__(self, index: int | None, name: str | None, width: int = 1280, height: int = 720):
        super().__init__()
        self.index = index
        self.name = name
        self.size = (width, height)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"webcam-{self.name}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _resolve_index(self) -> int | None:
        # the index can change when devices are plugged/unplugged: prefer the name
        cams = list_webcams()
        for cam in cams:
            if self.name and cam.name == self.name:
                return cam.index
        return self.index if any(c.index == self.index for c in cams) else None

    def _run(self) -> None:
        while not self._stop.is_set():
            index = self._resolve_index()
            if index is None:
                self.status = tr("webcam not found: {name}", name=self.name)
                self._stop.wait(2)
                continue
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                self.status = tr("webcam not available (maybe in use by another app): {name}", name=self.name)
                cap.release()
                self._stop.wait(2)
                continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.size[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.size[1])
            self.status = ""
            failures = 0
            while not self._stop.is_set() and failures < 30:
                ok, frame = cap.read()
                if ok and frame is not None:
                    self._frame = frame  # BGR
                    failures = 0
                else:
                    failures += 1
                    self._stop.wait(0.05)
            cap.release()
            if not self._stop.is_set():
                self.status = tr("webcam disconnected: {name}", name=self.name)
                self._stop.wait(1)
