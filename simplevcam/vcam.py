"""Virtual camera control: starts/stops the simpleVCam camera and feeds it frames.

The camera is the native media source in native/ (installed by the installer, or by scripts/install_vcam.ps1).
Windows loads it inside the Frame Server service, which creates the shared section
SECTION_NAME when an app opens the camera; we open that section and write BGRA frames into it.
Layout and names must match native/src/SharedFrame.h and native/src/Common.h.
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
import winreg
from ctypes import wintypes

import numpy as np

from .i18n import tr

CLSID = "{5FF39D7F-AB7D-467D-8A8F-9D45DFE61F9C}"
FRIENDLY_NAME = "simpleVCam"
SECTION_NAME = "Global\\simpleVCam_Frame"
DATA_DIR = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "simpleVCam")
CONFIG_FILE = os.path.join(DATA_DIR, "output.cfg")
LOG_FILE = os.path.join(DATA_DIR, "vcam.log")

HEADER_SIZE = 64
MAGIC = 0x4D435653  # 'SVCM'
VERSION = 1
MAX_WIDTH, MAX_HEIGHT = 3840, 2160
SECTION_SIZE = HEADER_SIZE + MAX_WIDTH * MAX_HEIGHT * 4
FILETIME_UNIX_EPOCH = 116444736000000000  # 1970-01-01 in 100 ns units since 1601

_REOPEN_INTERVAL = 0.5  # seconds between attempts to open the section while no app watches the camera


class VCamError(RuntimeError):
    pass


def not_installed_message() -> str:
    if getattr(sys, "frozen", False):  # packaged app: the installer registers the camera
        return tr("The virtual camera is not installed: reinstall simpleVCam.")
    return tr("The virtual camera is not installed: run scripts\\install_vcam.ps1 as administrator.")


def installed_dll_path() -> str | None:
    """Path of the registered camera DLL, or None if the camera is not installed."""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"Software\Classes\CLSID\{CLSID}\InprocServer32") as key:
            path, _ = winreg.QueryValueEx(key, "")
    except OSError:
        return None
    return path if os.path.isfile(path) else None


class FrameWriter:
    """Writes BGRA frames into a buffer laid out as SharedHeader + pixels.

    `seq` is a seqlock: odd while a frame is being written, even when it is complete,
    so the reader can detect and retry torn reads.
    """

    def __init__(self, buffer):
        self._buffer = buffer
        self._fields = np.frombuffer(buffer, dtype=np.uint32, count=6, offset=0)  # magic..fps
        self._seq = np.frombuffer(buffer, dtype=np.int64, count=1, offset=24)
        self._timestamp = np.frombuffer(buffer, dtype=np.int64, count=1, offset=32)

    def write(self, frame: np.ndarray, fps: int) -> None:
        height, width = frame.shape[:2]
        if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 4:
            raise ValueError("frame must be a HxWx4 uint8 BGRA array")
        if width > MAX_WIDTH or height > MAX_HEIGHT:
            raise ValueError(f"frame larger than {MAX_WIDTH}x{MAX_HEIGHT}")

        seq = int(self._seq[0])
        if seq & 1:  # a previous writer died mid-frame
            seq += 1
        self._seq[0] = seq + 1
        self._fields[:] = (MAGIC, VERSION, width, height, width * 4, fps)
        pixels = np.frombuffer(self._buffer, dtype=np.uint8, count=height * width * 4, offset=HEADER_SIZE)
        np.copyto(pixels.reshape(height, width, 4), frame)
        self._timestamp[0] = time.time_ns() // 100 + FILETIME_UNIX_EPOCH
        self._seq[0] = seq + 2


class _Section:
    """Read/write view of the named section created by the camera."""

    _FILE_MAP_WRITE = 0x0002
    _FILE_MAP_READ = 0x0004

    def __init__(self):
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        k32.OpenFileMappingW.restype = wintypes.HANDLE
        k32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
        k32.MapViewOfFile.restype = ctypes.c_void_p
        k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._k32 = k32
        self._handle = None
        self._address = None
        self.buffer = None

    def open(self) -> bool:
        access = self._FILE_MAP_READ | self._FILE_MAP_WRITE
        handle = self._k32.OpenFileMappingW(access, False, SECTION_NAME)
        if not handle:
            return False
        address = self._k32.MapViewOfFile(handle, access, 0, 0, SECTION_SIZE)
        if not address:
            self._k32.CloseHandle(handle)
            return False
        self._handle, self._address = handle, address
        self.buffer = (ctypes.c_ubyte * SECTION_SIZE).from_address(address)
        return True

    def close(self) -> None:
        self.buffer = None
        if self._address:
            self._k32.UnmapViewOfFile(self._address)
            self._address = None
        if self._handle:
            self._k32.CloseHandle(self._handle)
            self._handle = None


class VirtualCamera:
    """Creates the "simpleVCam" device while running and forwards frames to it."""

    def __init__(self, dll_path: str | None = None):
        self.dll_path = dll_path or installed_dll_path()
        self._dll = None
        self._section = None
        self._writer: FrameWriter | None = None
        self._last_open_attempt = 0.0
        self._fps = 30
        self.running = False

    @property
    def available(self) -> bool:
        return self.dll_path is not None

    @property
    def connected(self) -> bool:
        """True once an app has opened the camera (the shared section exists)."""
        return self._writer is not None

    def _load(self):
        if self._dll is None:
            if not self.available:
                raise VCamError(not_installed_message())
            dll = ctypes.WinDLL(self.dll_path)
            dll.SvcStart.argtypes = [wintypes.LPCWSTR]
            dll.SvcStart.restype = ctypes.c_long
            dll.SvcStop.argtypes = []
            dll.SvcStop.restype = ctypes.c_long
            self._dll = dll
        return self._dll

    def start(self, width: int, height: int, fps: int) -> None:
        if self.running:
            self.stop()
        if width % 2 or height % 2:
            raise VCamError(tr("Width and height must be even."))
        dll = self._load()
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="ascii") as f:
                f.write(f"{width} {height} {fps}\n")
        except OSError as e:
            raise VCamError(tr("Cannot write {path}: {error}", path=CONFIG_FILE, error=e)) from e

        hr = dll.SvcStart(FRIENDLY_NAME)
        if hr < 0:
            raise VCamError(tr("Starting the virtual camera failed (HRESULT 0x{hr:08X}).", hr=hr & 0xFFFFFFFF))
        self._fps = fps
        self._section = _Section()
        self._last_open_attempt = 0.0
        self.running = True

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        self._writer = None
        if self._section:
            self._section.close()
            self._section = None
        self._dll.SvcStop()

    def send(self, frame: np.ndarray) -> None:
        """Publishes a BGRA frame; a no-op until some app opens the camera."""
        if not self.running:
            return
        if self._writer is None:
            now = time.monotonic()
            if now - self._last_open_attempt < _REOPEN_INTERVAL:
                return
            self._last_open_attempt = now
            if not self._section.open():
                return
            self._writer = FrameWriter(self._section.buffer)
        self._writer.write(frame, self._fps)
