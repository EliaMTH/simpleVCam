import struct
import time

import numpy as np
import pytest

from simplevcam.vcam import FILETIME_UNIX_EPOCH, HEADER_SIZE, MAGIC, VERSION, FrameWriter


def header(buf):
    magic, version, w, h, stride, fps, seq, ts = struct.unpack_from("<6Iqq", buf, 0)
    return dict(magic=magic, version=version, width=w, height=h, stride=stride, fps=fps, seq=seq, timestamp=ts)


def test_writes_header_and_pixels():
    buf = bytearray(HEADER_SIZE + 8 * 6 * 4)
    frame = np.arange(6 * 8 * 4, dtype=np.uint8).reshape(6, 8, 4)
    FrameWriter(buf).write(frame, 30)

    h = header(buf)
    assert (h["magic"], h["version"], h["width"], h["height"], h["stride"], h["fps"]) == (MAGIC, VERSION, 8, 6, 32, 30)
    assert h["seq"] == 2  # even: frame complete
    now = time.time_ns() // 100 + FILETIME_UNIX_EPOCH
    assert 0 <= now - h["timestamp"] < 10_000_000
    assert bytes(buf[HEADER_SIZE:]) == frame.tobytes()


def test_seq_advances_and_recovers_from_torn_write():
    buf = bytearray(HEADER_SIZE + 2 * 2 * 4)
    writer = FrameWriter(buf)
    frame = np.zeros((2, 2, 4), np.uint8)
    writer.write(frame, 30)
    writer.write(frame, 30)
    assert header(buf)["seq"] == 4
    struct.pack_into("<q", buf, 24, 7)  # a writer crashed mid-frame
    writer.write(frame, 30)
    assert header(buf)["seq"] == 10


def test_rejects_wrong_format():
    writer = FrameWriter(bytearray(HEADER_SIZE + 64))
    with pytest.raises(ValueError):
        writer.write(np.zeros((2, 2, 3), np.uint8), 30)
