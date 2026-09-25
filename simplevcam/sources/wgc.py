"""Screen and window capture through Windows Graphics Capture (windows-capture package)."""
from __future__ import annotations

import threading

from windows_capture import WindowsCapture

from ..i18n import tr
from .base import Source


class WgcSource(Source):
    """Runs a capture session and restarts it when it ends (e.g. the window was closed and reopened)."""

    max_fps = 120  # WGC never delivers faster than the display refresh rate anyway

    def __init__(self):
        super().__init__()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def capture_target(self) -> dict | None:
        """WindowsCapture arguments selecting what to capture, or None if it is not available now."""
        raise NotImplementedError

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=type(self).__name__, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            target = self.capture_target()
            if target is None:
                self._stop.wait(1)
                continue

            closed = threading.Event()
            try:
                capture = WindowsCapture(cursor_capture=True, draw_border=False,
                                         minimum_update_interval=1000 // self.max_fps, **target)

                @capture.event
                def on_frame_arrived(frame, control):
                    if self._stop.is_set():
                        control.stop()
                        return
                    self._frame = frame.frame_buffer.copy()  # the buffer is only valid during the callback

                @capture.event
                def on_closed():
                    closed.set()

                control = capture.start_free_threaded()
            except Exception as e:
                self.status = tr("capture failed: {error}", error=e)
                self._stop.wait(2)
                continue

            self.status = ""
            while not self._stop.is_set() and not closed.is_set() and not control.is_finished():
                self._stop.wait(0.5)
            try:
                control.stop()
            except Exception:
                pass
            if not self._stop.is_set():
                self.capture_ended()

    def capture_ended(self) -> None:
        """Called when the session ends by itself (target closed)."""
        self._frame = None
        self._stop.wait(1)
