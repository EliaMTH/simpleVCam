"""Draws the layers of a scene onto a BGRA canvas.

Per layer: source frame -> mask -> crop -> scale -> position (like OBS).
"""
from __future__ import annotations

import cv2
import numpy as np

from .model import Layer


def new_canvas(width: int, height: int) -> np.ndarray:
    canvas = np.zeros((height, width, 4), np.uint8)
    canvas[..., 3] = 255
    return canvas


class Compositor:
    def __init__(self):
        # layer id -> (key, mask resized to the displayed size)
        self._mask_cache: dict[str, tuple[tuple, np.ndarray]] = {}
        self._black: np.ndarray | None = None

    def compose(self, canvas: np.ndarray, layers: list[Layer], frames: dict[str, np.ndarray | None]) -> None:
        """Clears `canvas` (HxWx4 BGRA) and draws `layers` bottom to top.

        `frames` maps layer id -> latest source frame (BGRA or BGR), or None if not available.
        """
        if self._black is None or self._black.shape != canvas.shape:
            self._black = new_canvas(canvas.shape[1], canvas.shape[0])
        np.copyto(canvas, self._black)  # much faster than per-channel assignment
        for layer in layers:
            frame = frames.get(layer.id)
            if frame is not None:
                self._draw(canvas, layer, frame)
        live = {l.id for l in layers}
        for stale in self._mask_cache.keys() - live:
            del self._mask_cache[stale]

    def _draw(self, canvas: np.ndarray, layer: Layer, frame: np.ndarray) -> None:
        sh, sw = frame.shape[:2]
        c = layer.crop
        x0, y0, x1, y1 = c.left, c.top, sw - c.right, sh - c.bottom
        if x1 <= x0 or y1 <= y0:
            return
        cw, ch = x1 - x0, y1 - y0

        t = layer.transform
        dw, dh = round(cw * t.scale_x), round(ch * t.scale_y)
        if dw <= 0 or dh <= 0:
            return
        dx, dy = round(t.x), round(t.y)

        # part of the destination rectangle that falls inside the canvas
        H, W = canvas.shape[:2]
        vx0, vy0 = max(dx, 0), max(dy, 0)
        vx1, vy1 = min(dx + dw, W), min(dy + dh, H)
        if vx1 <= vx0 or vy1 <= vy0:
            return

        cropped = frame[y0:y1, x0:x1]
        interp = cv2.INTER_AREA if dw < cw or dh < ch else cv2.INTER_LINEAR
        scaled = cropped if (dw, dh) == (cw, ch) else cv2.resize(cropped, (dw, dh), interpolation=interp)
        src = scaled[vy0 - dy:vy1 - dy, vx0 - dx:vx1 - dx]
        dst = canvas[vy0:vy1, vx0:vx1]

        # Work on 4 channels with OpenCV: whole-pixel copies are an order of magnitude
        # faster than per-channel numpy slices or integer blending.
        if src.shape[2] == 3:
            src = cv2.cvtColor(src, cv2.COLOR_BGR2BGRA)  # opaque
            alpha = None
        else:
            alpha = cv2.extractChannel(src, 3)
            if cv2.minMaxLoc(alpha)[0] >= 255:
                alpha = None  # opaque

        mask = self._scaled_mask(layer, (sw, sh), (dw, dh))
        if mask is not None:
            mask = mask[vy0 - dy:vy1 - dy, vx0 - dx:vx1 - dx]
            if alpha is None:
                cv2.copyTo(src, mask, dst)  # binary: copy where visible, in place
                return
            alpha = cv2.min(alpha, mask)

        if alpha is None:
            dst[...] = src
            return
        if cv2.minMaxLoc(alpha)[1] == 0:
            return
        a = alpha.astype(np.float32) * (1.0 / 255.0)
        dst[...] = cv2.blendLinear(src, dst, a, 1.0 - a)

    def _scaled_mask(self, layer: Layer, source_size: tuple[int, int], display_size: tuple[int, int]) -> np.ndarray | None:
        """The layer mask adapted to the current source size, cropped and scaled to the displayed size."""
        if layer.mask is None:
            return None
        key = (layer.mask_version, id(layer.mask), source_size, layer.crop.as_tuple(), display_size)
        cached = self._mask_cache.get(layer.id)
        if cached and cached[0] == key:
            return cached[1]

        mask = layer.mask
        sw, sh = source_size
        if mask.shape[:2] != (sh, sw):
            # the source changed size since the mask was drawn (e.g. a resized window)
            mask = cv2.resize(mask, (sw, sh), interpolation=cv2.INTER_NEAREST)
        c = layer.crop
        mask = mask[c.top:sh - c.bottom, c.left:sw - c.right]
        if (mask.shape[1], mask.shape[0]) != display_size:
            mask = cv2.resize(mask, display_size, interpolation=cv2.INTER_NEAREST)
        self._mask_cache[layer.id] = (key, mask)
        return mask
