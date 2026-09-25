from __future__ import annotations

from .wgc import WgcSource
from .winutil import list_monitors


class ScreenSource(WgcSource):
    def __init__(self, monitor: int):
        super().__init__()
        self.monitor = monitor

    def capture_target(self) -> dict | None:
        if not any(m.index == self.monitor for m in list_monitors()):
            self.status = f"monitor {self.monitor} non trovato"
            return None
        return {"monitor_index": self.monitor}
