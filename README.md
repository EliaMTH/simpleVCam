# simpleVCam

Virtual camera for Windows 11. It composes screens, windows, images and webcams
and shows them to other apps (Teams, Zoom, Meet in the browser, the Camera app) as the **simpleVCam** webcam.

## Requirements

- Windows 11
- `MFCreateVirtualCamera`
- Python 3.12
- Visual Studio Build Tools with C++, the Windows SDK and CMake, only to build the camera DLL

## Installation

```bat
:: 1. Python environment
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

:: 2. virtual camera DLL
native\build.bat

:: 3. camera registration, one time only, from PowerShell as administrator
powershell -ExecutionPolicy Bypass -File scripts\install_vcam.ps1
```

The installer copies the DLL to `C:\Program Files\simpleVCam`, because the Windows Frame Server services cannot
read it from user folders. It then registers it and creates `C:\ProgramData\simpleVCam`, which holds
`output.cfg` and `vcam.log`. If you rebuild the DLL, close simpleVCam and run `install_vcam.ps1` again.

To remove the camera: `scripts\uninstall_vcam.ps1`, as administrator.

## Running

`run.bat`, or `.venv\Scripts\python -m simplevcam`.

The user interface is in Italian; the labels below are quoted as they appear in the app.

- **Preview**: click to select a layer, drag it to move it, drag a corner to resize it
  (Shift = free aspect ratio). The arrow keys move it by 1 px (Shift: 10 px).
- **Top bar**: save and load presets, output resolution and fps (15, 30, 60 or 120; the default is 60),
  "Specchia uscita" to mirror the whole image sent to the camera, and the camera switch.
- **Layers**: the first one in the list is in front. To change the order, drag the layers in the list,
  or use ▲ and ▼. Position, size, mirroring (horizontal and vertical) and crop can also be set in the
  properties panel.
- **Mask**: a binary image as large as the source, where red marks the hidden area.
  The tools are brush, rectangle and ellipse; holding Ctrl turns the rectangle into a square and the
  ellipse into a circle. The left mouse button applies the selected mode (hide by default), the right
  button the opposite. There are also show all, hide all and invert, Ctrl+Z to undo and Ctrl+wheel to zoom.
  The mask is applied before crop and mirroring, so it stays on the source content.
- **"Avvia camera"** (start camera): creates the "simpleVCam" device, which disappears when you stop it or
  close the app. DirectShow apps list it as "simpleVCam (Windows Virtual Camera)", with the suffix in the
  Windows language (e.g. "Fotocamera virtuale di Windows" on Italian Windows).

Notes:
- A webcam used as a source stays busy while simpleVCam uses it: in the other apps, pick "simpleVCam".
- Output resolution and fps are fixed while the camera is on. If you change them, the camera is recreated and
  connected apps may need to select it again. "Specchia uscita" does not recreate it.
- While the camera is on but no app is connected, the app sends no frames.

## Presets

Readable JSON. Masks are PNG files in the `<preset name>_masks` folder next to the file.
`layers[0]` is the bottom layer.

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

## Structure

- `simplevcam/`: the app
  - `model.py`, `presets.py`: scene and presets
  - `compositor.py`: mask → crop → scale → mirror → position
  - `engine.py`: rendering loop
  - `vcam.py`: camera control and shared memory
  - `sources/`: the sources
  - `ui/`: the user interface
- `native/`: the camera's C++ DLL, a Media Foundation media source derived from
  [VCamSample](https://github.com/smourier/VCamSample) (MIT). It reads frames from the shared section
  `Global\simpleVCam_Frame`, created by the Frame Server service and written by the app.
- `scripts/`: camera installation and self-test

## Tests

```bat
.venv\Scripts\python -m pytest
.venv\Scripts\python scripts\vcam_selftest.py [fps]
```

`vcam_selftest.py` starts the camera, sends it a known pattern and reads it back through DirectShow and
Media Foundation. It needs the camera installed. If something goes wrong, check `C:\ProgramData\simpleVCam\vcam.log`.
