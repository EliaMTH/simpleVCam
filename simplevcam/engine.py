"""Rendering loop: collects source frames, composes the scene, feeds the camera and the preview."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from .animations import AnimationPlayer, Slot
from .compositor import Compositor, new_canvas
from .model import AnimationPlacement, Layer, OutputSettings, Scene, animation_placement
from .sources import Source, create_source
from .vcam import VirtualCamera

PREVIEW_MAX_FPS = 60


@dataclass
class _Playback:
    """An animation playing over the output."""

    player: AnimationPlayer
    default: Layer  # its placement while the scene has none for the slot: own size, centered


class Engine(QObject):
    preview_ready = Signal(QImage)
    layers_changed = Signal()  # a layer was auto-fitted after its first frame
    fps_measured = Signal(float)

    def __init__(self):
        super().__init__()
        self.scene = Scene()
        self.camera = VirtualCamera()
        self._lock = threading.RLock()  # protects scene.layers structure and _sources
        self._camera_lock = threading.Lock()
        self._sources: dict[str, Source] = {}
        self._pending_fit: set[str] = set()
        self._playbacks: dict[int, _Playback] = {}  # slot -> playing animation, in start order (the last on top)
        self._animation_errors: dict[int, str] = {}  # slot -> why its last playback stopped early
        self._editing: int | None = None  # slot being positioned: looped, shown in the preview only
        self._compositor = Compositor()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # --- scene -----------------------------------------------------------------

    def set_scene(self, scene: Scene) -> None:
        with self._lock:
            for source in self._sources.values():
                source.stop()
            self._sources.clear()
            self._pending_fit.clear()
            self.scene = scene
            for layer in scene.layers:
                self._start_source(layer)
        self._camera_follow_output()

    def add_layer(self, layer: Layer, fit: bool = True) -> None:
        with self._lock:
            self.scene.layers.append(layer)
            self._start_source(layer)
            if fit:
                self._pending_fit.add(layer.id)

    def remove_layer(self, layer_id: str) -> None:
        with self._lock:
            self.scene.layers = [l for l in self.scene.layers if l.id != layer_id]
            source = self._sources.pop(layer_id, None)
            self._pending_fit.discard(layer_id)
        if source:
            source.stop()

    def move_layer(self, layer_id: str, delta: int) -> None:
        """delta > 0 moves the layer up (drawn later, on top)."""
        with self._lock:
            layers = self.scene.layers
            i = next((i for i, l in enumerate(layers) if l.id == layer_id), None)
            if i is None:
                return
            j = max(0, min(len(layers) - 1, i + delta))
            layers.insert(j, layers.pop(i))

    def set_layer_order(self, ids: list[str]) -> None:
        """Reorders the layers as `ids` (bottom to top); unknown ids are ignored, missing layers keep their place at the end."""
        with self._lock:
            by_id = {l.id: l for l in self.scene.layers}
            ordered = [by_id.pop(i) for i in ids if i in by_id]
            self.scene.layers = ordered + list(by_id.values())

    def set_output(self, output: OutputSettings) -> None:
        with self._lock:
            previous = self.scene.output
            self.scene.output = output
        if not output.same_format(previous):
            self._camera_follow_output()

    def source_status(self, layer_id: str) -> str:
        source = self._sources.get(layer_id)
        return source.status if source else ""

    def latest_frame(self, layer_id: str) -> np.ndarray | None:
        source = self._sources.get(layer_id)
        return source.latest_frame() if source else None

    def _start_source(self, layer: Layer) -> None:
        source = create_source(layer.source)
        self._sources[layer.id] = source
        source.start()

    def pickable_layers(self) -> list[Layer]:
        """Layers the preview can select, bottom to top: the scene's, then the animation being positioned."""
        with self._lock:
            layers = list(self.scene.layers)
            placement = self.scene.animations.get(self._editing) if self._editing is not None else None
        return layers + [placement] if placement is not None else layers

    # --- animations ------------------------------------------------------------

    def play_animation(self, slot: Slot) -> None:
        """Plays the slot's animation over all layers, as many times as its placement says (once without one);
        playing it again restarts it."""
        if slot.playable:
            placement = self.scene.animations.get(slot.index)
            self._start_playback(slot, placement.plays if placement is not None else 1)

    def stop_animation(self, index: int) -> None:
        with self._lock:
            playback = self._playbacks.pop(index, None)
        if playback:
            playback.player.stop()

    def animation_playing(self, index: int) -> bool:
        playback = self._playbacks.get(index)
        return playback is not None and not playback.player.finished

    def animation_error(self, index: int) -> str:
        """Why the last playback of the slot stopped early, or ""."""
        return self._animation_errors.get(index, "")

    def animation_layer(self, slot: Slot) -> AnimationPlacement:
        """The slot's placement in the scene, created (own size, centered) if missing: presets then save it."""
        with self._lock:
            layer = self.scene.animations.get(slot.index)
            if layer is None:
                layer = animation_placement(slot.index)
                layer.source_size = slot.size
                layer.center_native(self.scene.output)
                self.scene.animations[slot.index] = layer
            elif slot.size:
                layer.source_size = slot.size  # the file may have changed since the last frame
        return layer

    def edit_animation(self, slot: Slot | None) -> None:
        """Loops the slot's animation while it is being positioned: in the preview only, the camera never gets it.
        None ends the positioning."""
        if self._editing is not None:
            self.stop_animation(self._editing)  # first, or the loop would reach the camera for a frame
        with self._lock:
            self._editing = slot.index if slot is not None else None
        if slot is not None and slot.playable:
            self._start_playback(slot, plays=None)

    def _start_playback(self, slot: Slot, plays: int | None) -> None:
        default = animation_placement(slot.index)
        default.source_size = slot.size
        default.center_native(self.scene.output)
        player = AnimationPlayer(slot.data, plays)
        with self._lock:
            previous = self._playbacks.pop(slot.index, None)
            self._playbacks[slot.index] = _Playback(player, default)  # (re)inserted last: drawn on top
            self._animation_errors.pop(slot.index, None)
            player.start()
        if previous:
            previous.player.stop()

    def _animation_layers(self, frames: dict[str, np.ndarray | None]) -> tuple[list[Layer], Layer | None]:
        """Placements of the playing animations, bottom to top, and of the one being positioned (or None); adds
        their current frames to `frames` and forgets the finished ones. Called with the lock held."""
        playing, editing = [], None
        for index, playback in list(self._playbacks.items()):
            player = playback.player
            if player.finished:
                del self._playbacks[index]
                if player.status:
                    self._animation_errors[index] = player.status
                continue
            frame = player.latest_frame()
            if frame is None:
                continue
            layer = self.scene.animations.get(index)  # looked up every frame: a loaded preset applies at once
            if layer is None:
                layer = playback.default
            layer.source_size = (frame.shape[1], frame.shape[0])
            frames[layer.id] = frame
            if index == self._editing:
                editing = layer
            else:
                playing.append(layer)
        return playing, editing

    # --- camera ----------------------------------------------------------------

    @property
    def camera_running(self) -> bool:
        return self.camera.running

    @property
    def camera_connected(self) -> bool:
        return self.camera.connected

    def start_camera(self) -> None:
        out = self.scene.output
        with self._camera_lock:
            self.camera.start(out.width, out.height, out.fps)

    def stop_camera(self) -> None:
        with self._camera_lock:
            self.camera.stop()

    def _camera_follow_output(self) -> None:
        # the camera announces a fixed format: recreate it when the output changes
        if self.camera.running:
            self.stop_camera()
            self.start_camera()

    # --- loop ------------------------------------------------------------------

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="engine", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self.stop_camera()
        with self._lock:
            for source in self._sources.values():
                source.stop()
            self._sources.clear()
            playbacks = list(self._playbacks.values())
            self._playbacks.clear()
        for playback in playbacks:
            playback.player.stop()

    def _run(self) -> None:
        canvas = None
        next_tick = time.perf_counter()
        frames_done, fps_since = 0, time.perf_counter()
        while not self._stop.is_set():
            fitted = False
            with self._lock:
                out = self.scene.output
                layers = list(self.scene.layers)
                frames = {}
                for layer in layers:
                    source = self._sources.get(layer.id)
                    frame = source.latest_frame() if source else None
                    frames[layer.id] = frame
                    if frame is not None:
                        layer.source_size = (frame.shape[1], frame.shape[0])
                        if layer.id in self._pending_fit:
                            layer.fit_to(out)
                            self._pending_fit.discard(layer.id)
                            fitted = True
                animations, editing = self._animation_layers(frames)

            if canvas is None or canvas.shape[:2] != (out.height, out.width):
                canvas = new_canvas(out.width, out.height)
            # animations go over all layers, before the output mirroring like everything else
            self._compositor.compose(canvas, layers + animations, frames)
            result = cv2.flip(canvas, 1) if out.mirror else canvas

            with self._camera_lock:
                try:
                    self.camera.send(result)
                except Exception as e:  # never let a camera problem stop the preview
                    print("camera send failed:", e)

            # the camera gets every frame; the preview at most PREVIEW_MAX_FPS (repainting costs GUI time)
            if frames_done % max(1, round(out.fps / PREVIEW_MAX_FPS)) == 0:
                shown = result
                if editing is not None:  # the animation being positioned: added to the preview only
                    shown = canvas.copy()
                    self._compositor.draw(shown, [editing], frames)
                    if out.mirror:
                        shown = cv2.flip(shown, 1)
                image = QImage(shown.data, out.width, out.height, out.width * 4, QImage.Format.Format_RGB32).copy()
                self.preview_ready.emit(image)
            if fitted:
                self.layers_changed.emit()

            frames_done += 1
            now = time.perf_counter()
            if now - fps_since >= 1.0:
                self.fps_measured.emit(frames_done / (now - fps_since))
                frames_done, fps_since = 0, now

            next_tick += 1.0 / max(1, out.fps)
            delay = next_tick - time.perf_counter()
            if delay > 0:
                time.sleep(delay)  # high-resolution timer on Windows (unlike Event.wait)
            elif delay < -0.25:  # fell far behind: don't try to catch up
                next_tick = time.perf_counter()
