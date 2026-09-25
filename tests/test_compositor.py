import numpy as np

from simplevcam.compositor import Compositor, new_canvas
from simplevcam.model import Crop, Layer, SourceSpec, Transform


def solid(w, h, bgr, alpha=255):
    frame = np.empty((h, w, 4), np.uint8)
    frame[..., :3] = bgr
    frame[..., 3] = alpha
    return frame


def layer(x=0, y=0, sx=1.0, sy=1.0, crop=None):
    return Layer(SourceSpec("image", path="x.png"), "l", Transform(x, y, sx, sy), crop or Crop())


def compose(layers, frames, w=100, h=80):
    canvas = new_canvas(w, h)
    Compositor().compose(canvas, layers, frames)
    return canvas


def test_empty_scene_is_black():
    canvas = compose([], {})
    assert (canvas[..., :3] == 0).all() and (canvas[..., 3] == 255).all()


def test_position_and_order():
    bottom, top = layer(0, 0), layer(10, 10)
    canvas = compose([bottom, top], {bottom.id: solid(30, 30, (255, 0, 0)), top.id: solid(30, 30, (0, 0, 255))})
    assert tuple(canvas[5, 5, :3]) == (255, 0, 0)
    assert tuple(canvas[20, 20, :3]) == (0, 0, 255)  # top wins where they overlap
    assert tuple(canvas[35, 35, :3]) == (0, 0, 255)
    assert tuple(canvas[45, 45, :3]) == (0, 0, 0)


def test_scale():
    l = layer(0, 0, 2.0, 0.5)
    canvas = compose([l], {l.id: solid(10, 20, (0, 255, 0))})
    assert (canvas[:10, :20, 1] == 255).all()
    assert (canvas[10:, :, 1] == 0).all() and (canvas[:, 20:, 1] == 0).all()


def test_crop():
    frame = solid(20, 20, (0, 0, 0))
    frame[:, 10:] = (255, 255, 255, 255)  # right half white
    l = layer(0, 0, crop=Crop(left=10))
    canvas = compose([l], {l.id: frame})
    assert (canvas[:20, :10, :3] == 255).all()  # only the white half remains, moved to x=0
    assert (canvas[:, 10:, :3] == 0).all()


def test_clipping_outside_canvas():
    l = layer(-5, 70)
    canvas = compose([l], {l.id: solid(20, 20, (9, 9, 9))})
    assert (canvas[70:80, 0:15, :3] == 9).all()
    assert (canvas[:70, :, :3] == 0).all()
    fully_outside = layer(500, 500)
    compose([fully_outside], {fully_outside.id: solid(20, 20, (9, 9, 9))})  # must not raise


def test_alpha_blend():
    bottom, top = layer(), layer()
    canvas = compose([bottom, top], {bottom.id: solid(10, 10, (0, 0, 200)), top.id: solid(10, 10, (200, 0, 0), alpha=128)})
    b, g, r = (int(v) for v in canvas[5, 5, :3])
    assert abs(b - 100) <= 1 and g == 0 and abs(r - 100) <= 1


def test_mask():
    l = layer()
    mask = np.zeros((10, 10), np.uint8)
    mask[:, :5] = 255
    l.set_mask(mask)
    canvas = compose([l], {l.id: solid(10, 10, (255, 255, 255))})
    assert (canvas[:10, :5, :3] == 255).all()
    assert (canvas[:10, 5:10, :3] == 0).all()


def test_mask_applies_before_crop_and_scale():
    l = layer(0, 0, 2.0, 2.0, crop=Crop(left=4))
    mask = np.zeros((10, 10), np.uint8)
    mask[:, 6:] = 255  # visible from source x=6
    l.set_mask(mask)
    canvas = compose([l], {l.id: solid(10, 10, (255, 255, 255))})
    # after cropping 4 px the visible part starts at x=2, scaled x2 -> 4
    assert (canvas[:20, :4, :3] == 0).all()
    assert (canvas[:20, 4:12, :3] == 255).all()


def test_mask_follows_source_resize():
    l = layer()
    mask = np.zeros((10, 10), np.uint8)
    mask[:, :5] = 255  # left half
    l.set_mask(mask)
    canvas = compose([l], {l.id: solid(40, 20, (255, 255, 255))})  # source grew to 40x20
    assert (canvas[:20, :20, :3] == 255).all()
    assert (canvas[:20, 20:40, :3] == 0).all()


def test_bgr_frames_are_opaque():
    l = layer()
    canvas = compose([l], {l.id: np.full((10, 10, 3), 77, np.uint8)})
    assert (canvas[:10, :10, :3] == 77).all()


def test_missing_frame_is_skipped():
    l = layer()
    canvas = compose([l], {l.id: None})
    assert (canvas[..., :3] == 0).all()


def test_flip_horizontal_keeps_mask_on_content():
    frame = solid(10, 4, (0, 0, 0))
    frame[:, :3] = (255, 255, 255, 255)  # white on the left of the source
    l = layer()
    l.transform.flip_h = True
    mask = np.full((4, 10), 255, np.uint8)
    mask[:, :1] = 0  # hide the first source column
    l.set_mask(mask)
    canvas = compose([l], {l.id: frame})
    # mirrored: the white block is on the right, and the hidden column (source x=0) is the last one
    assert (canvas[:4, 7:9, :3] == 255).all()
    assert (canvas[:4, 9, :3] == 0).all()
    assert (canvas[:4, :7, :3] == 0).all()


def test_flip_vertical_with_clipping():
    frame = solid(4, 10, (0, 0, 0))
    frame[:2] = (255, 255, 255, 255)  # white on top of the source
    l = layer(0, -5)  # top 5 rows outside the canvas
    l.transform.flip_v = True
    canvas = compose([l], {l.id: frame})
    # mirrored: white at the bottom (layer rows 8-9 -> canvas rows 3-4)
    assert (canvas[3:5, :4, :3] == 255).all()
    assert (canvas[0:3, :4, :3] == 0).all()
