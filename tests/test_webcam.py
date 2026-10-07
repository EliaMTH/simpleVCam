import threading
import time

import numpy as np
import pytest

from simplevcam.sources import webcam
from simplevcam.sources.webcam import WebcamSource
from simplevcam.sources.winutil import WebcamInfo, com_initialized


def wait_for(condition, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.01)
    return False


class FakeCapture:
    """A DirectShow capture: delivers its frames, then stalls. Like OpenCV's, a frame that doesn't come
    leaves retrieve() failing with a blank image (read() would call it a good frame)."""

    def __init__(self, frames: list[np.ndarray] | None):
        self.frames = frames  # None: endless frames of 2
        self.released = False

    def isOpened(self):
        return True

    def grab(self):
        return not self.released

    def retrieve(self):
        if self.frames is None:
            time.sleep(0.001)
            return True, np.full((4, 4, 3), 2, np.uint8)
        if self.frames:
            return True, self.frames.pop(0)
        time.sleep(0.01)  # OpenCV waits up to a second
        return False, np.zeros((4, 4, 3), np.uint8)

    def release(self):
        self.released = True


@pytest.fixture
def cams(monkeypatch):
    found = [WebcamInfo(0, "Cam")]
    monkeypatch.setattr(webcam, "list_webcams", lambda: list(found))
    return found


def test_a_stalled_camera_is_opened_again(monkeypatch, cams):
    monkeypatch.setattr(webcam, "STALL_TIMEOUT", 0.2)
    source = WebcamSource(0, "Cam")
    captures, status_on_reopen = [], []

    def open_capture(index, api, params):
        if captures:
            status_on_reopen.append(source.status)
        captures.append(FakeCapture([np.full((4, 4, 3), 1, np.uint8)] if not captures else None))
        return captures[-1]

    monkeypatch.setattr(webcam.cv2, "VideoCapture", open_capture)
    source.start()
    try:
        assert wait_for(lambda: source.latest_frame() is not None and source.latest_frame()[0, 0, 0] == 2)
    finally:
        source.stop()
    assert len(captures) == 2 and captures[0].released
    assert status_on_reopen == ["webcam not responding: Cam"]
    assert source.status == ""


def test_the_blank_image_of_a_missing_frame_is_not_shown(monkeypatch, cams):
    capture = FakeCapture([np.full((4, 4, 3), 1, np.uint8)])
    monkeypatch.setattr(webcam.cv2, "VideoCapture", lambda index, api, params: capture)
    source = WebcamSource(0, "Cam")
    source.start()
    try:
        assert wait_for(lambda: source.latest_frame() is not None)
        time.sleep(0.1)  # a few missing frames
        assert source.latest_frame()[0, 0, 0] == 1
    finally:
        source.stop()


def test_webcams_can_be_listed_from_another_thread():
    from pygrabber.dshow_graph import FilterGraph

    FilterGraph()  # comtypes is imported here: it initializes COM for this thread only
    errors = []

    def list_devices():
        with com_initialized():
            try:
                FilterGraph().get_input_devices()
            except OSError as e:  # CO_E_NOTINITIALIZED
                errors.append(e)

    thread = threading.Thread(target=list_devices)
    thread.start()
    thread.join()
    assert not errors


def test_index_by_name(monkeypatch):
    def resolve(index, name, found):
        monkeypatch.setattr(webcam, "list_webcams", lambda: found)
        return WebcamSource(index, name)._resolve_index()

    # the webcam is missing: another camera with its index is not used instead
    assert resolve(0, "Cam", [WebcamInfo(0, "OBS Virtual Camera")]) is None
    assert resolve(0, "Cam", [WebcamInfo(0, "OBS Virtual Camera"), WebcamInfo(1, "Cam")]) == 1
    # same name: the saved index chooses
    assert resolve(2, "Cam", [WebcamInfo(0, "Cam"), WebcamInfo(2, "Cam")]) == 2
    assert resolve(5, "Cam", [WebcamInfo(0, "Cam"), WebcamInfo(2, "Cam")]) == 0
    # no name: the index alone
    assert resolve(1, None, [WebcamInfo(0, "A"), WebcamInfo(1, "B")]) == 1
    assert resolve(3, None, [WebcamInfo(0, "A")]) is None
