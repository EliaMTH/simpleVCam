from __future__ import annotations

import threading
import time

import cv2

from ..i18n import tr
from .base import Source
from .winutil import com_initialized, list_webcams

STALL_TIMEOUT = 5.0  # seconds without frames before the camera is opened again

# OpenCV's DirectShow backend keeps one process-wide, unsynchronized table of devices by index: captures of the
# same webcam share the device, and releasing one stops it for all. Opening and releasing go one at a time.
_dshow_lock = threading.Lock()


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
        # the index can change when devices are plugged/unplugged or a virtual camera starts: go by name, the
        # index only chooses among cameras with the same name. Without the camera (e.g. still waking up after
        # sleep) the saved index would open whatever other camera has it now, and stay there.
        cams = list_webcams()
        if self.name:
            indexes = [cam.index for cam in cams if cam.name == self.name]
            return self.index if self.index in indexes else next(iter(indexes), None)
        return self.index if any(c.index == self.index for c in cams) else None

    def _run(self) -> None:
        with com_initialized():  # for list_webcams()
            self._capture()

    def _capture(self) -> None:
        while not self._stop.is_set():
            index = self._resolve_index()
            if index is None:
                self.status = tr("webcam not found: {name}", name=self.name)
                self._stop.wait(2)
                continue
            # the size goes to the constructor: set() afterwards would start the camera, stop it and start it again
            params = [cv2.CAP_PROP_FRAME_WIDTH, self.size[0], cv2.CAP_PROP_FRAME_HEIGHT, self.size[1]]
            with _dshow_lock:
                cap = cv2.VideoCapture(index, cv2.CAP_DSHOW, params)
                opened = cap.isOpened()
                if not opened:
                    cap.release()
            if not opened:
                self.status = tr("webcam not available (maybe in use by another app): {name}", name=self.name)
                self._stop.wait(2)
                continue
            # not cap.read(): when no frame comes within a second, DirectShow gives it a blank (black) image as a
            # good frame, so a stalled camera would stay black for good. grab() fails once the device is lost.
            last_frame = time.monotonic()
            stalled = False
            while not self._stop.is_set() and cap.grab():
                ok, frame = cap.retrieve()
                if ok and frame is not None:
                    self._frame = frame  # BGR
                    self.status = ""
                    last_frame = time.monotonic()
                elif time.monotonic() - last_frame > STALL_TIMEOUT:
                    stalled = True
                    break
                else:
                    self._stop.wait(0.05)
            with _dshow_lock:
                cap.release()
            if not self._stop.is_set():
                self.status = (tr("webcam not responding: {name}", name=self.name) if stalled
                               else tr("webcam disconnected: {name}", name=self.name))
                self._stop.wait(1)
