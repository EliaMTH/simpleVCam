"""Save/load a Scene as a readable JSON file.

Masks are stored as PNG files in a "<preset>_masks" folder next to the JSON,
referenced by a path relative to the JSON file.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .i18n import tr
from .model import Crop, Layer, OutputSettings, Scene, SourceSpec, Transform

PRESET_VERSION = 1


def _mask_dir(json_path: Path) -> Path:
    return json_path.with_name(f"{json_path.stem}_masks")


def write_png(path: Path, image: np.ndarray) -> None:
    # cv2.imwrite does not handle non-ASCII paths on Windows
    ok, data = cv2.imencode(".png", image)
    if not ok:
        raise OSError(tr("cannot encode {name}", name=path.name))
    path.write_bytes(data.tobytes())


def read_image(path: Path, flags: int) -> np.ndarray | None:
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, flags) if data.size else None


def save_preset(scene: Scene, path: str | Path) -> None:
    path = Path(path)
    mask_dir = _mask_dir(path)
    layers = []
    used_masks = set()
    for layer in scene.layers:
        mask_ref = None
        if layer.mask is not None:
            mask_dir.mkdir(parents=True, exist_ok=True)
            mask_file = mask_dir / f"{layer.id}.png"
            write_png(mask_file, layer.mask)
            used_masks.add(mask_file.name)
            mask_ref = mask_file.relative_to(path.parent).as_posix()
        layers.append({
            "id": layer.id,
            "name": layer.name,
            "source": layer.source.to_dict(),
            "transform": layer.transform.to_dict(),
            "crop": layer.crop.to_dict(),
            "mask": mask_ref,
        })

    data = {"version": PRESET_VERSION, "output": scene.output.to_dict(), "layers": layers}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # remove masks of layers that no longer exist or no longer have a mask
    if mask_dir.is_dir():
        for stale in mask_dir.glob("*.png"):
            if stale.name not in used_masks:
                stale.unlink()
        if not any(mask_dir.iterdir()):
            mask_dir.rmdir()


def load_preset(path: str | Path) -> Scene:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data.get("version", 1)
    if version > PRESET_VERSION:
        raise ValueError(tr("preset version {version} not supported (maximum {maximum})", version=version, maximum=PRESET_VERSION))

    scene = Scene(output=OutputSettings.from_dict(data.get("output", {})))
    for d in data.get("layers", []):
        layer = Layer(
            source=SourceSpec.from_dict(d["source"]),
            name=d.get("name") or d["source"]["type"],
            transform=Transform.from_dict(d.get("transform", {})),
            crop=Crop.from_dict(d.get("crop", {})),
        )
        if d.get("id"):
            layer.id = str(d["id"])
        if d.get("mask"):
            mask = read_image(path.parent / d["mask"], cv2.IMREAD_GRAYSCALE)
            if mask is None:
                raise ValueError(tr("unreadable mask: {path}", path=d["mask"]))
            layer.set_mask(mask)
        scene.layers.append(layer)
    return scene
