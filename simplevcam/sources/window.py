from __future__ import annotations

from ..i18n import tr
from ..model import SourceSpec
from .wgc import WgcSource
from .winutil import find_window, is_window, process_exe, window_pid, window_title


class WindowSource(WgcSource):
    """Captures one window. If it closes, it looks for it again (same title, else same executable)."""

    def __init__(self, spec: SourceSpec):
        super().__init__()
        self.spec = spec
        self.hwnd = spec.hwnd

    def capture_target(self) -> dict | None:
        if not is_window(self.hwnd):
            found = find_window(self.spec.title, self.spec.exe)
            if found is None:
                self.status = tr("window not found: {name}", name=self.spec.title or self.spec.exe)
                return None
            self.hwnd = found.hwnd
        # keep the spec current, so a saved preset finds the window again
        self.spec.title = window_title(self.hwnd) or self.spec.title
        self.spec.exe = process_exe(window_pid(self.hwnd)) or self.spec.exe
        self.spec.hwnd = self.hwnd
        return {"window_hwnd": self.hwnd}

    def capture_ended(self) -> None:
        self.hwnd = None
        super().capture_ended()
