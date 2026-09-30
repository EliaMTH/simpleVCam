"""Self-check of a build, packaged or not: `simpleVCam --smoke-test [report.txt]`.

Verifies that the native dependencies load and that the app can build its window and render a frame,
without a webcam, the virtual camera or user interaction. Used by the release build and CI.
Exit code 0 = all checks passed; the details go to the report file.
"""
from __future__ import annotations

import shutil
import tempfile
import time
import traceback
from pathlib import Path

import numpy as np


def run(report_path: str | None) -> int:
    report = Path(report_path) if report_path else Path(tempfile.gettempdir()) / "simplevcam_smoke.txt"
    lines: list[str] = []
    failed = False

    def check(name, fn):
        nonlocal failed
        try:
            lines.append(f"OK    {name}: {fn()}")
        except Exception:
            failed = True
            lines.append(f"FAIL  {name}\n{traceback.format_exc()}")

    tmp = Path(tempfile.mkdtemp(prefix="simplevcam_smoke_"))
    image_path = tmp / "layer.png"
    animation_path = tmp / "animation.webp"

    def write_animation():
        from PIL import Image

        # half-transparent red, then blue: WebP must keep the alpha
        frames = [Image.new("RGBA", (40, 30), color) for color in ((255, 0, 0, 128), (0, 0, 255, 128))]
        frames[0].save(animation_path, save_all=True, append_images=frames[1:], duration=1000, loop=0, lossless=True)

    def version():
        from . import __version__

        return __version__

    def opencv():
        import cv2

        return cv2.__version__

    def graphics_capture():
        import windows_capture  # noqa: F401

        return "loaded"

    def directshow():
        from pygrabber.dshow_graph import FilterGraph

        return f"{len(FilterGraph().get_input_devices())} video devices"

    def monitors():
        from .sources.winutil import list_monitors

        found = list_monitors()
        if not found:
            raise RuntimeError("no monitors found")
        return ", ".join(m.label for m in found)

    def windows():
        from .sources.winutil import list_windows

        return f"{len(list_windows())} windows"

    def presets():
        from .model import Layer, Scene, SourceSpec
        from .presets import load_preset, save_preset, write_png

        frame = np.zeros((60, 80, 4), np.uint8)
        frame[..., 1] = 255
        frame[..., 3] = 255
        write_png(image_path, frame)
        layer = Layer(SourceSpec("image", path=image_path.as_posix()), "test")
        mask = np.zeros((60, 80), np.uint8)
        mask[:, :40] = 255
        layer.set_mask(mask)
        save_preset(Scene(layers=[layer]), tmp / "preset.json")
        loaded = load_preset(tmp / "preset.json")
        if not np.array_equal(loaded.layers[0].mask, layer.mask):
            raise RuntimeError("mask changed after save/load")
        return "save/load ok"

    def animations():
        from .animations import decode_frames

        write_animation()
        frames = list(decode_frames(animation_path.read_bytes()))
        if len(frames) != 2 or tuple(frames[0][0][15, 20]) != (0, 0, 255, 128):
            raise RuntimeError("animated WebP decoded wrong")
        return f"animated WebP: {len(frames)} frames, alpha kept"

    def window_and_render():
        from PySide6.QtCore import QEventLoop, QTimer

        from .model import Layer, SourceSpec
        from .ui.main_window import MainWindow

        window = MainWindow()  # built but not shown
        try:
            layer = Layer(SourceSpec("image", path=image_path.as_posix()), "test")
            window.engine.add_layer(layer)
            deadline = time.monotonic() + 5
            while window.preview.image is None and time.monotonic() < deadline:
                loop = QEventLoop()
                QTimer.singleShot(50, loop.quit)
                loop.exec()
            if window.preview.image is None or layer.source_size is None:
                raise RuntimeError("no frame rendered")
            out = window.engine.scene.output
            color = window.preview.image.pixelColor(out.width // 2, out.height // 2)

            # an animation plays over the layer, centered
            from .animations import load_slot

            if not animation_path.exists():
                write_animation()
            slot_dir = tmp / "slot"
            slot_dir.mkdir()
            shutil.copy(animation_path, slot_dir)
            window.engine.play_animation(load_slot(1, slot_dir))
            deadline = time.monotonic() + 5
            while window.preview.image.pixelColor(out.width // 2, out.height // 2) == color and time.monotonic() < deadline:
                loop = QEventLoop()
                QTimer.singleShot(50, loop.quit)
                loop.exec()
            animated = window.preview.image.pixelColor(out.width // 2, out.height // 2)
            if animated == color:
                raise RuntimeError("the animation was not drawn")
            return (f"frame {window.preview.image.width()}x{window.preview.image.height()}, center {color.name()}, "
                    f"with the animation {animated.name()}")
        finally:
            window.close()
            window.engine.shutdown()

    def camera():
        from .vcam import installed_dll_path

        return installed_dll_path() or "not installed (not an error here)"

    try:
        for name, fn in (("version", version), ("opencv", opencv), ("graphics capture", graphics_capture),
                         ("directshow", directshow), ("monitors", monitors), ("windows", windows),
                         ("presets", presets), ("animations", animations), ("window and render", window_and_render),
                         ("camera dll", camera)):
            check(name, fn)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    lines.append("RESULT: " + ("FAILED" if failed else "PASSED"))
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if failed else 0
