"""Collects the full license texts of everything the installer ships into one folder.

    python packaging/collect_licenses.py <output folder>

Run with the Python environment used for the build: the texts come from the installed packages.
"""
from __future__ import annotations

import re
import shutil
import sys
from importlib.metadata import distribution
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Python packages bundled by PyInstaller (see requirements.txt)
PACKAGES = ["PySide6", "PySide6_Essentials", "shiboken6", "numpy", "opencv-python", "windows-capture",
            "pygrabber", "comtypes"]
# texts not shipped inside the packages
EXTRA = {
    "Qt-PySide6": [ROOT / "packaging" / "licenses" / "LGPL-3.0.txt", ROOT / "packaging" / "licenses" / "GPL-3.0.txt"],
    "VCamSample": [ROOT / "native" / "LICENSE-VCamSample.txt"],
    "Python": [Path(sys.base_prefix) / "LICENSE.txt"],
}
LICENSE_NAME = re.compile(r"(LICEN[SC]E|COPYING|NOTICE)", re.IGNORECASE)


def main() -> int:
    out = Path(sys.argv[1])
    if out.exists():
        shutil.rmtree(out)
    count = 0
    for name in PACKAGES:
        for f in distribution(name).files or []:
            # license files anywhere in the package, or anything in a dist-info "licenses" folder
            if LICENSE_NAME.match(f.name) or "licenses" in f.parts[:-1]:
                target = out / name / Path(*f.parts)  # keep the path: numpy has several LICENSE.txt
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f.locate(), target)
                count += 1
    for name, files in EXTRA.items():
        for f in files:
            if not f.is_file():
                raise FileNotFoundError(f)
            (out / name).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, out / name / f.name)
            count += 1
    print(f"{count} license files in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
