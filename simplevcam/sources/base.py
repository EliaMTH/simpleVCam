from __future__ import annotations

import numpy as np


class Source:
    """A frame provider. latest_frame() returns a BGRA or BGR array, or None if nothing is available.

    Implementations update their frame from a background thread; the engine only reads the
    latest reference, so no locking is needed (reference assignment is atomic).
    """

    def __init__(self):
        self._frame: np.ndarray | None = None
        self.status = ""  # human readable problem, shown in the UI; empty when all is fine

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def latest_frame(self) -> np.ndarray | None:
        return self._frame
