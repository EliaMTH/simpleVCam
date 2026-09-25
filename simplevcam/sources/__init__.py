from __future__ import annotations

from ..model import SourceSpec
from .base import Source


def create_source(spec: SourceSpec) -> Source:
    if spec.type == "screen":
        from .screen import ScreenSource

        return ScreenSource(spec.monitor or 1)
    if spec.type == "window":
        from .window import WindowSource

        return WindowSource(spec)
    if spec.type == "image":
        from .image import ImageSource

        return ImageSource(spec.path or "")
    if spec.type == "webcam":
        from .webcam import WebcamSource

        return WebcamSource(spec.index, spec.name)
    raise ValueError(f"tipo di source sconosciuto: {spec.type!r}")
