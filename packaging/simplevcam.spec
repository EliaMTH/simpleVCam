# PyInstaller spec: builds the app as a folder (build/dist/simpleVCam/simpleVCam.exe + _internal/).
# One folder instead of one file: faster start-up and fewer antivirus false positives.
# Run through packaging/build_release.ps1, or: python -m PyInstaller packaging/simplevcam.spec
import re
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

ROOT = Path(SPECPATH).parent
VERSION = re.search(r'__version__ = "(.+?)"', (ROOT / "simplevcam" / "__init__.py").read_text()).group(1)
ICON = ROOT / "simplevcam" / "assets" / "simplevcam.ico"

numbers = tuple(int(n) for n in (VERSION.split(".") + ["0", "0", "0"])[:4])
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("ProductName", "simpleVCam"),
            StringStruct("FileDescription", "simpleVCam - layer-based virtual camera"),
            StringStruct("FileVersion", VERSION),
            StringStruct("ProductVersion", VERSION),
            StringStruct("OriginalFilename", "simpleVCam.exe"),
            StringStruct("LegalCopyright", "MIT License"),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

a = Analysis(
    [str(ROOT / "simplevcam" / "__main__.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "simplevcam" / "assets"), "simplevcam/assets")],
    excludes=["tkinter", "pytest"],
)
# Binaries pulled in by the hooks that the app never uses (~65 MB):
UNUSED_BINARIES = (
    "opencv_videoio_ffmpeg",     # OpenCV video-file decoding: we only read webcams through DirectShow
    "opengl32sw.dll",            # software OpenGL fallback: the UI paints without OpenGL
    "qtvirtualkeyboardplugin",   # touch on-screen keyboard, and the Qt Quick/QML it needs:
    "Qt6VirtualKeyboard", "Qt6Quick", "Qt6Qml",
    "qpdf.dll", "Qt6Pdf",        # PDF image format plugin
)
a.binaries = [b for b in a.binaries if not any(name.lower() in b[0].lower() for name in UNUSED_BINARIES)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="simpleVCam",
    console=False,
    icon=str(ICON),
    version=version_info,
    upx=False,  # UPX-packed files trigger more antivirus false positives
)
coll = COLLECT(exe, a.binaries, a.datas, name="simpleVCam", upx=False)
