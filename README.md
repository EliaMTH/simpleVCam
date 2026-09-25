# simpleVCam

Virtual camera for Windows 11. It composes screens, windows, images and webcams
and shows them to other apps (Teams, Zoom, Meet in the browser, the Camera app) as the **simpleVCam** webcam.

## Download

Requires Windows 11 (64-bit).

1. Download `simpleVCam-<last version>-setup.exe` from the
   [latest release](https://github.com/EliaMTH/simpleVCam/releases/latest) and run it. It asks for
   administrator rights because it registers the virtual camera with Windows.
2. Open **simpleVCam** from the Start menu, add your sources and press **Start camera**.
3. In Teams, Zoom, the browser, etc., pick **simpleVCam** as the camera.

The installer is not code-signed, so Windows SmartScreen may show "Windows protected your PC": choose
"More info" → "Run anyway". To check that the file is the published one, compare its hash with the `.sha256`
file of the release (PowerShell: `Get-FileHash simpleVCam-<version>-setup.exe`).

To uninstall: Settings → Apps → Installed apps → simpleVCam.

## Usage

The app is available in **English** and **Italian**: choose it from the **Language** menu in the top bar
(the change is immediate and remembered). On the first start it follows the Windows language.

- **Preview**: click to select a layer, drag it to move it, drag a corner to resize it
  (Shift = free aspect ratio). The arrow keys move it by 1 px (Shift: 10 px).
- **Top bar**: save and load presets, output resolution and fps (15, 30, 60 or 120; the default is 60),
  **Mirror output** to mirror the whole image sent to the camera, the language, and the camera switch.
- **Layers**: the first one in the list is in front. To change the order, drag the layers in the list,
  or use ▲ and ▼. Position, size, mirroring (horizontal and vertical) and crop can also be set in the
  properties panel.
- **Mask**: a binary image as large as the source, where red marks the hidden area.
  The tools are brush, rectangle and ellipse; holding Ctrl turns the rectangle into a square and the
  ellipse into a circle. The left mouse button applies the selected mode (hide by default), the right
  button the opposite. There are also show all, hide all and invert, Ctrl+Z to undo and Ctrl+wheel to zoom.
  The mask is applied before crop and mirroring, so it stays on the source content.
- **Start camera**: creates the "simpleVCam" device, which disappears when you stop it or close the app.
  DirectShow apps list it as "simpleVCam (Windows Virtual Camera)", with the suffix in the Windows language.

Notes:
- A webcam used as a source stays busy while simpleVCam uses it: in the other apps, pick "simpleVCam".
- Output resolution and fps are fixed while the camera is on. If you change them, the camera is recreated and
  connected apps may need to select it again. **Mirror output** does not recreate it.
- While the camera is on but no app is connected, the app sends no frames.

## Presets

Readable JSON. Masks are PNG files in the `<preset name>_masks` folder next to the file.
`layers[0]` is the bottom layer. The installed app saves presets in `Documents\simpleVCam` by default,
the app run from the sources in `presets\`.

```json
{
  "version": 1,
  "output": {"width": 1280, "height": 720, "fps": 60, "mirror": false},
  "layers": [
    {
      "id": "a1b2c3d4",
      "name": "Schermo 1",
      "source": {"type": "screen", "monitor": 1},
      "transform": {"x": 0, "y": 0, "scale_x": 0.666667, "scale_y": 0.666667, "flip_h": false, "flip_v": false},
      "crop": {"left": 0, "top": 0, "right": 0, "bottom": 0},
      "mask": "my_preset_masks/a1b2c3d4.png"
    }
  ]
}
```

`source` types and the fields they use:

| Type | Fields |
|---|---|
| `screen` | `monitor`, starting from 1 |
| `window` | `title`, `exe` |
| `image` | `path` |
| `webcam` | `index`, `name` |

A window is found again by exact title, otherwise by exe. A webcam is found again by name, otherwise by index.

## Build from source

Requirements:
- Windows 11 (the camera uses `MFCreateVirtualCamera`)
- Python 3.12
- Visual Studio Build Tools with C++, the Windows SDK and CMake, to build the camera DLL
- Inno Setup 6, only to build the installer (`winget install JRSoftware.InnoSetup`)

```bat
:: 1. Python environment
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt

:: 2. virtual camera DLL
native\build.bat

:: 3. camera registration, one time only, from PowerShell as administrator
powershell -ExecutionPolicy Bypass -File scripts\install_vcam.ps1

:: 4. run
run.bat
```

`install_vcam.ps1` copies the DLL to `C:\Program Files\simpleVCam`, because the Windows Frame Server services
cannot read it from user folders. It then registers it and creates `C:\ProgramData\simpleVCam`, which holds
`output.cfg` and `vcam.log`. If you rebuild the DLL, close simpleVCam and run `install_vcam.ps1` again.
To remove the camera: `scripts\uninstall_vcam.ps1`, as administrator.

The script and the installer register the same camera in the same place: installing one replaces the other.

### Tests

```bat
.venv\Scripts\python -m pytest
.venv\Scripts\python scripts\vcam_selftest.py [fps]
```

`vcam_selftest.py` starts the camera, sends it a known pattern and reads it back through DirectShow and
Media Foundation. It needs the camera installed. If something goes wrong, check `C:\ProgramData\simpleVCam\vcam.log`.

`simpleVCam.exe --smoke-test [report.txt]` (or `python -m simplevcam --smoke-test`) checks that a build
starts and renders, without a webcam or the camera; the release build runs it on the packaged app.

### Installer and releases

```bat
powershell -ExecutionPolicy Bypass -File packaging\build_release.ps1
```

This builds the camera DLL, runs the tests, packages the app with PyInstaller, smoke-tests the packaged exe and
creates `dist\simpleVCam-<version>-setup.exe` with its `.sha256`.

Releases are built by GitHub Actions (`.github/workflows/release.yml`):
1. set the new version in `simplevcam/__init__.py` (`__version__`) and commit;
2. `git tag v<version>` and `git push origin v<version>`;
3. the workflow builds the installer and creates a **draft** release with it attached: review the notes on
   GitHub and press "Publish release".

The workflow fails if the tag doesn't match `__version__`. It can also be started by hand from the Actions tab
(Release → Run workflow): it then only builds, and the installer is downloadable from the run's artifacts.

## Structure

- `simplevcam/`: the app
  - `model.py`, `presets.py`: scene and presets
  - `compositor.py`: mask → crop → scale → mirror → position
  - `engine.py`: rendering loop
  - `vcam.py`: camera control and shared memory
  - `sources/`: the sources
  - `ui/`: the user interface
  - `i18n.py`: user interface texts and their Italian translations
  - `smoke.py`: self-check of a build
- `native/`: the camera's C++ DLL, a Media Foundation media source derived from
  [VCamSample](https://github.com/smourier/VCamSample) (MIT). It reads frames from the shared section
  `Global\simpleVCam_Frame`, created by the Frame Server service and written by the app.
- `scripts/`: camera installation for development, and the camera self-test
- `packaging/`: PyInstaller spec, Inno Setup script, release build script, icon generator, license texts
- `.github/workflows/release.yml`: release build

## License

MIT, see [LICENSE](LICENSE). Third-party components and their licenses are listed in
[packaging/THIRD-PARTY-NOTICES.txt](packaging/THIRD-PARTY-NOTICES.txt); the installer ships their full texts.
