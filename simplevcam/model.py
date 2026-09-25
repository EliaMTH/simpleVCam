"""Scene description: output settings and a stack of layers (index 0 = bottom)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import numpy as np

from .i18n import tr

SOURCE_TYPES = ("screen", "window", "image", "webcam")


@dataclass
class OutputSettings:
    width: int = 1280
    height: int = 720
    fps: int = 60
    mirror: bool = False  # flip the whole output horizontally

    def to_dict(self) -> dict:
        return {"width": self.width, "height": self.height, "fps": self.fps, "mirror": self.mirror}

    @classmethod
    def from_dict(cls, d: dict) -> OutputSettings:
        return cls(width=int(d.get("width", 1280)), height=int(d.get("height", 720)), fps=int(d.get("fps", 60)),
                   mirror=bool(d.get("mirror", False)))

    def same_format(self, other: OutputSettings) -> bool:
        """True if the camera would announce the same format (mirroring doesn't change it)."""
        return (self.width, self.height, self.fps) == (other.width, other.height, other.fps)


@dataclass
class Transform:
    """Position of the (cropped) source on the output canvas, in output pixels, its scale and mirroring."""

    x: float = 0.0
    y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    flip_h: bool = False  # mirror left-right
    flip_v: bool = False  # mirror top-bottom

    def to_dict(self) -> dict:
        return {k: v if isinstance(v, bool) else round(v, 6) for k, v in vars(self).items()}

    @classmethod
    def from_dict(cls, d: dict) -> Transform:
        return cls(**{k: type(default)(d.get(k, default)) for k, default in vars(cls()).items()})

    def flip_code(self) -> int | None:
        """cv2.flip code for the mirroring, or None if not mirrored."""
        if self.flip_h and self.flip_v:
            return -1
        if self.flip_h:
            return 1
        if self.flip_v:
            return 0
        return None


@dataclass
class Crop:
    """Pixels removed from each edge of the source."""

    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0

    def to_dict(self) -> dict:
        return dict(vars(self))

    @classmethod
    def from_dict(cls, d: dict) -> Crop:
        return cls(**{k: max(0, int(d.get(k, 0))) for k in vars(cls())})

    def as_tuple(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom


@dataclass
class SourceSpec:
    """What a layer shows. Only the fields relevant to `type` are used:

    - screen: monitor (1-based, as in Windows display order)
    - window: title, exe (used to find the window again when a preset is loaded)
    - image: path
    - webcam: index, name
    """

    type: str
    monitor: int | None = None
    title: str | None = None
    exe: str | None = None
    path: str | None = None
    index: int | None = None
    name: str | None = None
    # Runtime only: handle of the captured window (not saved, window handles change between sessions).
    hwnd: int | None = field(default=None, compare=False, repr=False)

    def to_dict(self) -> dict:
        return {k: v for k, v in vars(self).items() if v is not None and k != "hwnd"}

    @classmethod
    def from_dict(cls, d: dict) -> SourceSpec:
        if d.get("type") not in SOURCE_TYPES:
            raise ValueError(tr("unknown source type: {type}", type=repr(d.get("type"))))
        known = {k: d[k] for k in vars(cls("screen")) if k in d and k != "hwnd"}
        return cls(**known)


@dataclass
class Layer:
    source: SourceSpec
    name: str
    transform: Transform = field(default_factory=Transform)
    crop: Crop = field(default_factory=Crop)
    # Binary mask (uint8, 0 = hidden, 255 = visible) with the size of the source frame; None = all visible.
    mask: np.ndarray | None = field(default=None, compare=False, repr=False)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    # Runtime only (not saved): size (w, h) of the last source frame, and a counter bumped on mask edits.
    source_size: tuple[int, int] | None = field(default=None, compare=False, repr=False)
    mask_version: int = field(default=0, compare=False, repr=False)

    def set_mask(self, mask: np.ndarray | None) -> None:
        if mask is not None:
            if mask.ndim != 2:
                raise ValueError(tr("the mask must be a single-channel image"))
            mask = np.where(mask > 127, 255, 0).astype(np.uint8)
        self.mask = mask
        self.mask_version += 1

    def cropped_size(self, source_size: tuple[int, int] | None = None) -> tuple[int, int]:
        w, h = source_size or self.source_size or (0, 0)
        c = self.crop
        return max(0, w - c.left - c.right), max(0, h - c.top - c.bottom)

    def display_rect(self, source_size: tuple[int, int] | None = None) -> tuple[float, float, float, float]:
        """(x, y, w, h) of the layer on the output canvas."""
        cw, ch = self.cropped_size(source_size)
        t = self.transform
        return t.x, t.y, cw * t.scale_x, ch * t.scale_y

    def set_display_size(self, width: float, height: float) -> None:
        """Changes the scale so the cropped source is shown at width x height."""
        cw, ch = self.cropped_size()
        if cw > 0 and width > 0:
            self.transform.scale_x = width / cw
        if ch > 0 and height > 0:
            self.transform.scale_y = height / ch

    def fit_to(self, output: OutputSettings) -> None:
        """Scales (keeping the aspect ratio) and centers the layer on the canvas."""
        cw, ch = self.cropped_size()
        if cw <= 0 or ch <= 0:
            return
        s = min(output.width / cw, output.height / ch)
        t = self.transform  # keep the mirroring
        t.x, t.y = (output.width - cw * s) / 2, (output.height - ch * s) / 2
        t.scale_x = t.scale_y = s


@dataclass
class Scene:
    output: OutputSettings = field(default_factory=OutputSettings)
    layers: list[Layer] = field(default_factory=list)  # index 0 = bottom (drawn first)

    def layer_by_id(self, layer_id: str) -> Layer | None:
        return next((l for l in self.layers if l.id == layer_id), None)
