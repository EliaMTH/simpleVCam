import json

import numpy as np
import pytest

from simplevcam.model import Crop, Layer, OutputSettings, Scene, SourceSpec, Transform
from simplevcam.presets import load_preset, save_preset


def make_scene() -> Scene:
    mask = np.zeros((90, 160), np.uint8)
    mask[10:50, 20:100] = 255
    screen = Layer(SourceSpec("screen", monitor=1), "Schermo 1", Transform(10, 20, 0.5, 0.25), Crop(1, 2, 3, 4))
    screen.set_mask(mask)
    window = Layer(SourceSpec("window", title="Documento - Word", exe="WINWORD.EXE"), "Word")
    image = Layer(SourceSpec("image", path="C:/immagini/logo è.png"), "Logo", Transform(1.5, 2.5, 2 / 3, 1))
    webcam = Layer(SourceSpec("webcam", index=0, name="Microsoft LifeCam HD-3000"), "Webcam")
    webcam.transform.flip_h = True
    return Scene(OutputSettings(1920, 1080, 25, mirror=True), [screen, window, image, webcam])


def test_roundtrip(tmp_path):
    scene = make_scene()
    path = tmp_path / "mio preset.json"
    save_preset(scene, path)
    loaded = load_preset(path)

    assert loaded.output == scene.output
    assert [l.id for l in loaded.layers] == [l.id for l in scene.layers]
    for original, copy in zip(scene.layers, loaded.layers):
        assert copy.source == original.source
        assert copy.name == original.name
        assert copy.crop == original.crop
        assert copy.transform.x == pytest.approx(original.transform.x)
        assert copy.transform.scale_x == pytest.approx(original.transform.scale_x, abs=1e-6)
        assert (copy.transform.flip_h, copy.transform.flip_v) == (original.transform.flip_h, original.transform.flip_v)
        if original.mask is None:
            assert copy.mask is None
        else:
            assert np.array_equal(copy.mask, original.mask)


def test_json_is_readable(tmp_path):
    path = tmp_path / "p.json"
    save_preset(make_scene(), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["output"] == {"width": 1920, "height": 1080, "fps": 25, "mirror": True}
    first = data["layers"][0]
    assert first["source"] == {"type": "screen", "monitor": 1}
    assert first["mask"] == f"p_masks/{first['id']}.png"
    assert (tmp_path / first["mask"]).is_file()
    assert data["layers"][1]["mask"] is None
    assert data["layers"][2]["source"]["path"] == "C:/immagini/logo è.png"
    assert data["layers"][3]["transform"]["flip_h"] is True


def test_stale_masks_are_removed(tmp_path):
    scene = make_scene()
    path = tmp_path / "p.json"
    save_preset(scene, path)
    scene.layers[0].set_mask(None)
    save_preset(scene, path)
    assert not (tmp_path / "p_masks").exists()


def test_mask_is_binarized():
    layer = Layer(SourceSpec("image", path="x.png"), "x")
    layer.set_mask(np.array([[0, 100, 128, 255]], np.uint8))
    assert layer.mask.tolist() == [[0, 0, 255, 255]]


def test_unknown_source_type():
    with pytest.raises(ValueError):
        SourceSpec.from_dict({"type": "banana"})


def test_geometry():
    layer = Layer(SourceSpec("screen", monitor=1), "s", Transform(0, 0, 1, 1), Crop(10, 0, 10, 20))
    layer.source_size = (1920, 1080)
    assert layer.cropped_size() == (1900, 1060)
    layer.set_display_size(950, 530)
    assert layer.display_rect() == (0, 0, 950, 530)
    layer.fit_to(OutputSettings(1280, 720))
    x, y, w, h = layer.display_rect()
    assert w <= 1280 and h <= 720
    assert (w == pytest.approx(1280)) or (h == pytest.approx(720))
    assert x == pytest.approx((1280 - w) / 2) and y == pytest.approx((720 - h) / 2)


def test_fit_keeps_mirroring():
    layer = Layer(SourceSpec("webcam", index=0), "w")
    layer.source_size = (640, 480)
    layer.transform.flip_h = True
    layer.fit_to(OutputSettings(1280, 720))
    assert layer.transform.flip_h


def test_old_presets_without_mirroring_load():
    assert Transform.from_dict({"x": 1, "y": 2, "scale_x": 0.5, "scale_y": 0.5}).flip_h is False
    assert OutputSettings.from_dict({"width": 640, "height": 480, "fps": 30}).mirror is False
