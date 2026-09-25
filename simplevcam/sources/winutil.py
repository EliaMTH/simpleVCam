"""Win32 helpers: list monitors, top-level windows and webcams."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

_MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), _MONITORENUMPROC, wintypes.LPARAM]
user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]


user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFOEXW)]


@dataclass
class MonitorInfo:
    index: int  # 1-based, the order used by windows-capture
    device: str
    width: int
    height: int
    primary: bool

    @property
    def label(self) -> str:
        primary = " (principale)" if self.primary else ""
        return f"Monitor {self.index}: {self.width}×{self.height}{primary}"


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    exe: str

    @property
    def label(self) -> str:
        return f"{self.title} — {self.exe}"


@dataclass
class WebcamInfo:
    index: int  # DirectShow index, as used by cv2.VideoCapture(index, cv2.CAP_DSHOW)
    name: str


def list_monitors() -> list[MonitorInfo]:
    monitors: list[MonitorInfo] = []

    def callback(hmonitor, _hdc, _rect, _lparam):
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            r = info.rcMonitor
            monitors.append(MonitorInfo(len(monitors) + 1, info.szDevice, r.right - r.left, r.bottom - r.top, bool(info.dwFlags & 1)))
        return True

    user32.EnumDisplayMonitors(None, None, _MONITORENUMPROC(callback), 0)
    return monitors


def window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def process_exe(pid: int) -> str:
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return os.path.basename(buffer.value)
        return ""
    finally:
        kernel32.CloseHandle(handle)


def is_window(hwnd: int | None) -> bool:
    return bool(hwnd) and bool(user32.IsWindow(hwnd))


def _is_capturable(hwnd: int) -> bool:
    if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):  # GW_OWNER: skip owned popups
        return False
    ex_style = user32.GetWindowLongPtrW(hwnd, -20)  # GWL_EXSTYLE
    if ex_style & 0x80:  # WS_EX_TOOLWINDOW
        return False
    cloaked = wintypes.DWORD()
    dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))  # DWMWA_CLOAKED
    return not cloaked.value


def list_windows() -> list[WindowInfo]:
    """Visible top-level windows with a title, excluding this process (to avoid capturing ourselves)."""
    own_pid = os.getpid()
    windows: list[WindowInfo] = []

    def callback(hwnd, _lparam):
        if _is_capturable(hwnd):
            title = window_title(hwnd)
            pid = window_pid(hwnd)
            if title and pid != own_pid:
                windows.append(WindowInfo(int(hwnd), title, process_exe(pid)))
        return True

    user32.EnumWindows(_WNDENUMPROC(callback), 0)
    return windows


def find_window(title: str | None, exe: str | None) -> WindowInfo | None:
    """Finds a window by exact title, falling back to the first window of the same executable."""
    windows = list_windows()
    for w in windows:
        if title and w.title == title:
            return w
    for w in windows:
        if exe and w.exe.lower() == exe.lower():
            return w
    return None


def list_webcams(exclude_prefix: str = "simpleVCam") -> list[WebcamInfo]:
    """DirectShow video devices, without our own virtual camera (it would feed back into itself)."""
    try:
        from pygrabber.dshow_graph import FilterGraph

        names = FilterGraph().get_input_devices()
    except Exception:
        return []
    return [WebcamInfo(i, name) for i, name in enumerate(names) if not name.startswith(exclude_prefix)]
