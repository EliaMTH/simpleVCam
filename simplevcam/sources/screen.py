from __future__ import annotations

from ..i18n import tr
from .wgc import WgcSource
from .winutil import list_monitors


class ScreenSource(WgcSource):
    def __init__(self, monitor: int):
        super().__init__()
        self.monitor = monitor

    def capture_target(self) -> dict | None:
        if not any(m.index == self.monitor for m in list_monitors()):
            self.status = tr("monitor {index} not found", index=self.monitor)
            return None
        return {"monitor_index": self.monitor}
