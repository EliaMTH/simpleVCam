import time

import pytest
from PIL import Image

from simplevcam.animations import AnimationPlayer, decode_frames, load_slot, scan_slots

RED_HALF = (255, 0, 0, 128)
BLUE = (0, 0, 255, 255)


def save_animation(path, colors, durations, size=(8, 6), **options):
    frames = [Image.new("RGBA", size, color) for color in colors]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durations, loop=0, **options)
    return path


def wait_for(condition, timeout=3.0) -> bool:
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.005)
    return condition()


@pytest.mark.parametrize("name, options", [("a.webp", {"lossless": True}), ("a.png", {})])
def test_webp_and_apng_keep_soft_alpha(tmp_path, name, options):
    path = save_animation(tmp_path / name, [RED_HALF, BLUE], [50, 70], **options)
    frames = list(decode_frames(path.read_bytes()))
    assert len(frames) == 2
    (first, first_time), (second, second_time) = frames
    assert first.shape == (6, 8, 4)
    assert tuple(first[3, 4]) == (0, 0, 255, 128)  # BGRA, half transparent
    assert tuple(second[3, 4]) == (255, 0, 0, 255)
    assert (first_time, second_time) == (pytest.approx(0.05), pytest.approx(0.07))


def test_gif_transparency_is_on_or_off(tmp_path):
    path = save_animation(tmp_path / "a.gif", [(255, 0, 0, 0), BLUE], [50, 70])
    frames = [frame for frame, _ in decode_frames(path.read_bytes())]
    assert len(frames) == 2
    assert frames[0][3, 4, 3] == 0
    assert tuple(frames[1][3, 4]) == (255, 0, 0, 255)


def test_frames_without_duration_last_a_tenth_of_a_second(tmp_path):
    path = save_animation(tmp_path / "a.webp", [RED_HALF, BLUE], [0, 0], lossless=True)
    assert [seconds for _, seconds in decode_frames(path.read_bytes())] == [0.1, 0.1]


def test_scan_creates_the_slot_folders(tmp_path):
    root = tmp_path / "animations"
    slots = scan_slots(root)
    assert [slot.index for slot in slots] == list(range(1, 10))
    assert all((root / str(i)).is_dir() for i in range(1, 10))
    assert (root / "README.txt").is_file()
    assert all(slot.path is None and not slot.playable and not slot.error for slot in slots)


def test_slot_with_animation_and_icon(tmp_path):
    save_animation(tmp_path / "lightbulb.webp", [RED_HALF, BLUE], [50, 50], lossless=True)
    Image.new("RGB", (16, 16)).save(tmp_path / "icon.png")
    (tmp_path / "notes.txt").write_text("ignored")
    slot = load_slot(4, tmp_path)
    assert slot.index == 4
    assert slot.path.name == "lightbulb.webp" and slot.icon.name == "icon.png"
    assert slot.size == (8, 6)
    assert slot.playable and slot.error == ""
    assert slot.data == (tmp_path / "lightbulb.webp").read_bytes()


def test_an_apng_next_to_icon_png(tmp_path):
    Image.new("RGB", (16, 16)).save(tmp_path / "Icon.PNG")
    save_animation(tmp_path / "anim.png", [RED_HALF, BLUE], [50, 50])
    slot = load_slot(1, tmp_path)
    assert slot.icon.name == "Icon.PNG" and slot.path.name == "anim.png" and slot.playable


def test_a_still_image_is_not_an_animation(tmp_path):
    Image.new("RGBA", (8, 6)).save(tmp_path / "still.png")
    slot = load_slot(1, tmp_path)
    assert slot.error and not slot.playable


def test_an_unreadable_file(tmp_path):
    (tmp_path / "broken.webp").write_bytes(b"not an image")
    slot = load_slot(1, tmp_path)
    assert "broken.webp" in slot.error and not slot.playable


def test_player_plays_once_then_shows_nothing(tmp_path):
    data = save_animation(tmp_path / "a.webp", [RED_HALF, BLUE, RED_HALF], [30, 30, 30], lossless=True).read_bytes()
    player = AnimationPlayer(data)
    player.start()
    assert wait_for(lambda: player.latest_frame() is not None)
    assert wait_for(lambda: player.finished)
    assert player.latest_frame() is None and player.status == "" and player.played == 1


def test_player_plays_the_chosen_number_of_times(tmp_path):
    data = save_animation(tmp_path / "a.webp", [RED_HALF, BLUE], [20, 20], lossless=True).read_bytes()
    player = AnimationPlayer(data, plays=3)
    started = time.monotonic()
    player.start()
    assert wait_for(lambda: player.finished)
    assert player.played == 3 and time.monotonic() - started >= 0.1  # three rounds of 40 ms
    assert player.latest_frame() is None


def test_endless_player_goes_on_until_stopped(tmp_path):
    data = save_animation(tmp_path / "a.webp", [RED_HALF, BLUE], [20, 20], lossless=True).read_bytes()
    player = AnimationPlayer(data, plays=None)
    player.start()
    time.sleep(0.2)  # several rounds
    assert not player.finished and player.latest_frame() is not None
    player.stop()
    assert player.finished and player.latest_frame() is None


def test_player_reports_damaged_data():
    player = AnimationPlayer(b"not an image")
    player.start()
    assert wait_for(lambda: player.finished)
    assert player.status and player.latest_frame() is None
