"""End-to-end check of the virtual camera.

Starts "simpleVCam", feeds it a known pattern and reads it back like any other app would
(OpenCV through DirectShow and Media Foundation), comparing the colors of four quadrants.

    .venv\\Scripts\\python scripts\\vcam_selftest.py [fps]
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from simplevcam.vcam import FRIENDLY_NAME, LOG_FILE, VirtualCamera  # noqa: E402

WIDTH, HEIGHT = 1280, 720
FPS = int(sys.argv[1]) if len(sys.argv) > 1 else 60  # optional argument: frame rate
# BGR colors of the quadrants: top-left, top-right, bottom-left, bottom-right
QUADRANTS = [(0, 0, 255), (0, 255, 0), (255, 0, 0), (255, 255, 255)]
TOLERANCE = 24  # NV12 round trip and limited-range conversion


def pattern(t: float) -> np.ndarray:
    frame = np.zeros((HEIGHT, WIDTH, 4), np.uint8)
    frame[..., 3] = 255
    h2, w2 = HEIGHT // 2, WIDTH // 2
    for i, color in enumerate(QUADRANTS):
        y, x = (i // 2) * h2, (i % 2) * w2
        frame[y:y + h2, x:x + w2, :3] = color
    # a moving bar across the middle, to see that frames flow
    x = int((t * 300) % WIDTH)
    frame[h2 - 20:h2 + 20, max(0, x - 40):x + 40, :3] = (0, 200, 255)
    return frame


def feed(camera: VirtualCamera, stop: threading.Event) -> None:
    t0 = time.monotonic()
    while not stop.is_set():
        camera.send(pattern(time.monotonic() - t0))
        time.sleep(1 / FPS)


def find_device_index() -> int | None:
    from pygrabber.dshow_graph import FilterGraph

    devices = FilterGraph().get_input_devices()
    print("DirectShow devices:", devices)
    # Windows appends a localized "(Windows Virtual Camera)" to the name
    matches = [i for i, name in enumerate(devices) if name.startswith(FRIENDLY_NAME)]
    return matches[0] if matches else None


def check(api_name: str, api: int, index: int) -> bool:
    cap = cv2.VideoCapture(index, api)
    if not cap.isOpened():
        print(f"[{api_name}] cannot open device {index}")
        return False
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    frame = None
    deadline = time.monotonic() + 10
    good = 0
    first = 0.0
    while time.monotonic() < deadline and good < 60:
        ok, img = cap.read()
        if ok and img is not None and img.mean() > 5:  # skip initial black frames
            frame = img
            good += 1
            if good == 1:
                first = time.monotonic()
    cap.release()
    if good > 1:
        print(f"[{api_name}] {(good - 1) / (time.monotonic() - first):.1f} fps")
    if frame is None:
        print(f"[{api_name}] no frames received")
        return False

    h, w = frame.shape[:2]
    print(f"[{api_name}] got {w}x{h}")
    ok = (w, h) == (WIDTH, HEIGHT)
    for i, expected in enumerate(QUADRANTS):
        cy = (i // 2) * (h // 2) + h // 4
        cx = (i % 2) * (w // 2) + w // 4
        got = frame[cy - 10:cy + 10, cx - 10:cx + 10].reshape(-1, 3).mean(axis=0)
        diff = np.abs(got - np.array(expected)).max()
        print(f"[{api_name}] quadrant {i}: expected {expected} got {tuple(int(v) for v in got)} diff {diff:.0f}")
        ok &= diff <= TOLERANCE
    cv2.imwrite(str(Path(__file__).resolve().parent / f"selftest_{api_name}.png"), frame)
    return ok


def main() -> int:
    camera = VirtualCamera()
    if not camera.available:
        print("camera not installed")
        return 2
    print("DLL:", camera.dll_path)
    camera.start(WIDTH, HEIGHT, FPS)
    stop = threading.Event()
    feeder = threading.Thread(target=feed, args=(camera, stop), daemon=True)
    feeder.start()
    results = {}
    try:
        time.sleep(1)
        index = find_device_index()
        if index is None:
            print("simpleVCam not found among DirectShow devices")
            return 1
        results["dshow"] = check("dshow", cv2.CAP_DSHOW, index)
        results["msmf"] = check("msmf", cv2.CAP_MSMF, index)
        print("connected:", camera.connected)
    finally:
        stop.set()
        feeder.join()
        camera.stop()
        print("--- vcam.log (tail) ---")
        try:
            print("".join(Path(LOG_FILE).read_text(encoding="utf-8", errors="replace").splitlines(True)[-15:]))
        except OSError as e:
            print(e)
    print("results:", results)
    return 0 if results and all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
