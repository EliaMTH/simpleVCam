# simpleVCam

Virtual camera per Windows 11. Compone schermi, finestre, immagini e webcam
e li mostra alle altre app (Teams, Zoom, Meet nel browser, app Fotocamera) come la webcam **simpleVCam**.

## Requisiti

- Windows 11
- `MFCreateVirtualCamera`
- Python 3.12
- Visual Studio Build Tools con C++, Windows SDK e CMake, solo per compilare la DLL della camera

## Installazione

```bat
:: 1. ambiente Python
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

:: 2. DLL della virtual camera
native\build.bat

:: 3. registrazione della camera, una volta sola, da PowerShell come amministratore
powershell -ExecutionPolicy Bypass -File scripts\install_vcam.ps1
```

L'installazione copia la DLL in `C:\Program Files\simpleVCam`, perché i servizi Frame Server di Windows non
possono leggerla dalle cartelle utente. Poi la registra e crea `C:\ProgramData\simpleVCam`, che contiene
`output.cfg` e `vcam.log`. Se ricompili la DLL, chiudi simpleVCam e rilancia `install_vcam.ps1`.

Per rimuovere la camera: `scripts\uninstall_vcam.ps1`, da amministratore.

## Avvio

`run.bat`, oppure `.venv\Scripts\python -m simplevcam`.

- **Anteprima**: click per selezionare un layer, trascinalo per spostarlo, trascina un angolo per
  ridimensionarlo (Shift = proporzioni libere). Le frecce spostano di 1 px (Shift: 10 px).
- **Barra in alto**: salva e carica preset, risoluzione e fps di output (15, 30, 60 o 120; si parte da 60),
  "Specchia uscita" per specchiare tutta l'immagine inviata alla camera, accensione della camera.
- **Layer**: il primo della lista è in primo piano. Per cambiare l'ordine trascina i layer nella lista,
  oppure usa ▲ e ▼. Posizione, dimensione, specchio (orizzontale e verticale) e crop si impostano anche dal
  pannello proprietà.
- **Mask**: immagine binaria grande quanto la sorgente, in cui il rosso è la zona nascosta.
  Hai a disposizione pennello, rettangolo ed ellisse; con Ctrl premuto il rettangolo diventa un quadrato e
  l'ellisse un cerchio. Il tasto sinistro applica la modalità scelta (di default nasconde), il destro
  l'opposta. Ci sono anche mostra tutto, nascondi tutto e inverti, con Ctrl+Z per annullare e Ctrl+rotella
  per lo zoom. La mask viene applicata prima di crop e specchio, quindi resta sul contenuto della sorgente.
- **Avvia camera**: crea il device "simpleVCam", che sparisce quando la fermi o chiudi l'app.
  Nelle app DirectShow compare come "simpleVCam (Fotocamera virtuale di Windows)".

Note:
- Una webcam usata come sorgente resta occupata da simpleVCam: nelle altre app scegli "simpleVCam".
- Risoluzione e fps di output sono fissi finché la camera è accesa. Se li cambi, la camera viene ricreata e le
  app collegate potrebbero doverla riselezionare. "Specchia uscita" invece non la ricrea.
- Con la camera accesa ma nessuna app collegata, l'app non invia frame.

## Preset

JSON leggibile. Le mask sono PNG nella cartella `<nome preset>_masks` accanto al file.
`layers[0]` è il layer più in basso.

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
      "mask": "mio_preset_masks/a1b2c3d4.png"
    }
  ]
}
```

Tipi di `source` e campi usati:

| Tipo | Campi |
|---|---|
| `screen` | `monitor`, a partire da 1 |
| `window` | `title`, `exe` |
| `image` | `path` |
| `webcam` | `index`, `name` |

Una finestra si ritrova per titolo esatto oppure per exe. Una webcam si ritrova per nome oppure per indice.

## Struttura

- `simplevcam/`: l'app
  - `model.py`, `presets.py`: scena e preset
  - `compositor.py`: mask → crop → scala → specchio → posizione
  - `engine.py`: loop di rendering
  - `vcam.py`: controllo della camera e memoria condivisa
  - `sources/`: le sorgenti
  - `ui/`: l'interfaccia
- `native/`: DLL C++ della camera, un media source Media Foundation derivato da
  [VCamSample](https://github.com/smourier/VCamSample) (MIT). Legge i frame dalla sezione condivisa
  `Global\simpleVCam_Frame`, creata dal servizio Frame Server e scritta dall'app.
- `scripts/`: installazione della camera e self-test

## Test

```bat
.venv\Scripts\python -m pytest
.venv\Scripts\python scripts\vcam_selftest.py [fps]
```

`vcam_selftest.py` accende la camera, le invia un pattern noto e lo rilegge via DirectShow e Media Foundation.
Richiede la camera installata. In caso di problemi, guarda `C:\ProgramData\simpleVCam\vcam.log`.
