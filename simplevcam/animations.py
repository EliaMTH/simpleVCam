"""Soundboard animations: nine slot folders, each with an animated image and, optionally, the icon of its button.

    <animations folder>/1 … 9/
        icon.png         the button icon (any of ICON_SUFFIXES; optional)
        lightbulb.webp   the animation: the first file with one of ANIMATION_SUFFIXES not named icon.*

Animated WebP and APNG keep 8-bit transparency (soft edges, glows), GIF only on/off. Decoding uses Pillow,
which releases the GIL while it decodes, so an animation can play on its own thread next to the rendering loop.
"""
from __future__ import annotations

import io
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from .i18n import tr
from .model import ANIMATION_SLOTS
from .sources.base import Source

ANIMATION_SUFFIXES = (".webp", ".png", ".apng", ".gif")
ICON_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".ico")
DEFAULT_FRAME_TIME = 0.1  # seconds, for frames without a usable duration (what browsers do)

README = """\
simpleVCam - animations / animazioni

Folders 1-9 are the buttons of the Animations panel. In each folder put:
  - the animation: an animated WebP (recommended), APNG or GIF file, with any name;
  - optionally icon.png (or .jpg, .webp, .bmp, .ico): the icon of the button.
Transparent areas stay transparent: WebP and APNG have soft edges, GIF only fully visible or hidden pixels.
An animation plays once, at its own size and centered: "Adjust" in the panel sets how many times in a row it
plays (up to 10), and moves, resizes, crops or mirrors it; presets save that. After changing the files, press
"Reload".
A video with transparency (WebM, MOV) can be converted with ffmpeg, e.g.:
  ffmpeg -c:v libvpx-vp9 -i in.webm -c:v libwebp_anim -pix_fmt yuva420p -quality 85 -loop 0 out.webp

Le cartelle 1-9 sono i pulsanti del pannello Animazioni. In ogni cartella metti:
  - l'animazione: un file WebP animato (consigliato), APNG o GIF, con qualsiasi nome;
  - se vuoi, icon.png (o .jpg, .webp, .bmp, .ico): l'icona del pulsante.
Le zone trasparenti restano trasparenti: WebP e APNG hanno bordi morbidi, le GIF solo pixel pieni o vuoti.
Un'animazione parte una volta, alla sua dimensione e centrata: "Regola" nel pannello sceglie quante volte di
fila parte (fino a 10) e la sposta, la ridimensiona, la ritaglia o la specchia; i preset lo salvano. Dopo aver
cambiato i file, premi "Ricarica".
Un video con trasparenza (WebM, MOV) si converte con ffmpeg, per esempio:
  ffmpeg -c:v libvpx-vp9 -i in.webm -c:v libwebp_anim -pix_fmt yuva420p -quality 85 -loop 0 out.webp
"""


@dataclass
class Slot:
    index: int
    folder: Path
    icon: Path | None = None
    path: Path | None = None  # the animation file, None if the folder has none
    data: bytes | None = None  # its content, read once: playing needs no disk access
    size: tuple[int, int] | None = None  # (w, h)
    error: str = ""  # why the animation can't be played

    @property
    def playable(self) -> bool:
        return self.data is not None and not self.error


def scan_slots(root: Path) -> list[Slot]:
    """Reads the slot folders under `root`, creating them (and a README) if they are missing."""
    root.mkdir(parents=True, exist_ok=True)
    readme = root / "README.txt"
    if not readme.exists():
        readme.write_text(README, encoding="utf-8")
    slots = []
    for index in ANIMATION_SLOTS:
        folder = root / str(index)
        folder.mkdir(exist_ok=True)
        slots.append(load_slot(index, folder))
    return slots


def load_slot(index: int, folder: Path) -> Slot:
    slot = Slot(index, folder)
    files = sorted((p for p in folder.iterdir() if p.is_file()), key=lambda p: p.name.lower())
    slot.icon = next((p for p in files if p.stem.lower() == "icon" and p.suffix.lower() in ICON_SUFFIXES), None)
    slot.path = next((p for p in files if p.stem.lower() != "icon" and p.suffix.lower() in ANIMATION_SUFFIXES), None)
    if slot.path is None:
        return slot
    try:
        slot.data = slot.path.read_bytes()
        with Image.open(io.BytesIO(slot.data)) as image:  # reads the header only
            slot.size = image.size
            if not getattr(image, "is_animated", False):
                slot.error = tr("not an animation (a single image): {name}", name=slot.path.name)
    except UnidentifiedImageError:
        slot.error = tr("not a WebP, APNG or GIF image: {name}", name=slot.path.name)
    except Exception as e:  # e.g. the file can't be read
        slot.error = tr("animation not readable: {error}", error=e)
    return slot


def decode_frames(data: bytes) -> Iterator[tuple[np.ndarray, float]]:
    """The frames of an animated image as (BGRA frame, seconds to show it), each one complete as it is meant to be seen."""
    with Image.open(io.BytesIO(data)) as image:
        index = 0
        while True:
            try:
                image.seek(index)
            except EOFError:
                return
            rgba = np.asarray(image if image.mode == "RGBA" else image.convert("RGBA"))  # decodes the frame
            duration = (image.info.get("duration") or 0) / 1000  # WebP knows it only once the frame is decoded
            yield cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA), duration if duration > 0.01 else DEFAULT_FRAME_TIME
            index += 1


class AnimationPlayer(Source):
    """Plays an animation on a background thread: latest_frame() is the frame to show now, None once it is over.

    `plays` is how many times in a row it plays; None repeats it until stop().
    """

    def __init__(self, data: bytes, plays: int | None = 1):
        super().__init__()
        self.data = data
        self.plays = plays
        self.played = 0  # rounds played so far
        self.finished = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="animation", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    def _run(self) -> None:
        try:
            while not self._stop.is_set() and (self.plays is None or self.played < self.plays):
                self._play_once()
                self.played += 1
        except Exception as e:  # e.g. a file damaged after its header
            self.status = tr("animation not readable: {error}", error=e)
        finally:
            self._frame = None
            self.finished = True

    def _play_once(self) -> None:
        start = time.perf_counter()
        due = 0.0  # when the current frame should appear, in seconds from the start
        for frame, duration in decode_frames(self.data):
            if self._stop.is_set():
                return
            # if decoding fell behind, skip the frames whose time is already over
            if time.perf_counter() - start < due + duration:
                self._wait_until(start + due)
                self._frame = frame
            due += duration
        self._wait_until(start + due)  # the last frame stays for its duration

    def _wait_until(self, deadline: float) -> None:
        # time.sleep has a high-resolution timer on Windows (unlike Event.wait); short naps keep stop() quick
        while not self._stop.is_set():
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 0.05))
