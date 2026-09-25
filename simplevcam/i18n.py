"""User interface texts in English (the language of the code) and Italian.

    tr("Start camera")                  # "Avvia camera" when the language is Italian
    tr("Preset saved: {path}", path=p)  # placeholders are filled after translating

To add a text, call tr() with the English text and add its Italian translation to ITALIAN;
tests/test_i18n.py checks that every tr() text has a translation with the same placeholders.
Pure Python (no Qt), so model and sources can use it too.
"""
from __future__ import annotations

LANGUAGES = {"en": "English", "it": "Italiano"}  # code -> name shown in the language menu

_language = "en"


def set_language(code: str) -> None:
    global _language
    _language = code if code in LANGUAGES else "en"


def language() -> str:
    return _language


def tr(text: str, **values) -> str:
    if _language == "it":
        text = ITALIAN.get(text, text)
    return text.format(**values) if values else text


ITALIAN = {
    # main window
    "Save preset…": "Salva preset…",
    "Load preset…": "Carica preset…",
    "Output:": "Output:",
    "Mirror output": "Specchia uscita",
    "Mirrors the whole image sent to the camera (and the preview) horizontally":
        "Specchia orizzontalmente tutta l'immagine inviata alla camera (e l'anteprima)",
    "Language:": "Lingua:",
    "No source selected.": "Nessuna sorgente selezionata.",
    "The source hasn't produced any image yet: the mask needs its size.":
        "La sorgente non ha ancora prodotto immagini: la mask ha bisogno delle sue dimensioni.",
    "Save preset": "Salva preset",
    "Load preset": "Carica preset",
    "simpleVCam presets (*.json)": "Preset simpleVCam (*.json)",
    "Saving failed:\n{error}": "Salvataggio non riuscito:\n{error}",
    "Preset saved: {path}": "Preset salvato: {path}",
    "Loading failed:\n{error}": "Caricamento non riuscito:\n{error}",
    "Preset loaded: {path}": "Preset caricato: {path}",
    "Camera off": "Camera spenta",
    "Camera on — in use": "Camera accesa — in uso",
    "Camera on — no app connected": "Camera accesa — nessuna app collegata",
    "■  Stop camera": "■  Ferma camera",
    "●  Start camera": "●  Avvia camera",
    # layers panel
    "Screen": "Schermo",
    "Window": "Finestra",
    "Image": "Immagine",
    "Webcam": "Webcam",
    "monitor {index}": "monitor {index}",
    "+ Add": "+ Aggiungi",
    "− Remove": "− Rimuovi",
    "Move up": "Porta su",
    "Move down": "Porta giù",
    "Mask…": "Mask…",
    "Lock aspect ratio": "Blocca proporzioni",
    "Mirror horizontally": "Specchia orizzontale",
    "Mirror vertically": "Specchia verticale",
    "Fit to canvas": "Adatta al canvas",
    "Reset crop": "Reset crop",
    "Name": "Nome",
    "<b>Position and size</b> (output pixels)": "<b>Posizione e dimensione</b> (pixel di output)",
    "<b>Crop</b> (source pixels)": "<b>Crop</b> (pixel della sorgente)",
    "Left": "Sinistra",
    "Right": "Destra",
    "Top": "Sopra",
    "Bottom": "Sotto",
    "Properties": "Proprietà",
    "<b>Layers</b> — the one at the top of the list is in front.<br>Drag a layer up or down to change the order.":
        "<b>Layer</b> — quello in cima alla lista è in primo piano.<br>Trascina un layer su o giù per cambiare l'ordine.",
    # add source dialog
    "Add source": "Aggiungi sorgente",
    "Image path": "Percorso dell'immagine",
    "Refresh list": "Aggiorna elenco",
    "Browse…": "Sfoglia…",
    "Layer name": "Nome del layer",
    "Choose an image": "Scegli un'immagine",
    "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;All files (*)":
        "Immagini (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;Tutti i file (*)",
    "Screen {index}": "Schermo {index}",
    # mask editor
    "Mask — {name}": "Mask — {name}",
    "Tool:": "Strumento:",
    "Brush": "Pennello",
    "Rectangle": "Rettangolo",
    "Ellipse": "Ellisse",
    "Left button:": "Tasto sinistro:",
    "hides": "nasconde",
    "makes visible": "rende visibile",
    "Brush:": "Pennello:",
    "Show all": "Mostra tutto",
    "Hide all": "Nascondi tutto",
    "Invert": "Inverti",
    "Undo (Ctrl+Z)": "Annulla (Ctrl+Z)",
    "Fit": "Adatta",
    "Remove mask": "Rimuovi mask",
    "makes it <b>VISIBLE</b> (removes the red)": "rende <b>VISIBILE</b> (toglie il rosso)",
    "<b>HIDES</b> it (paints it red)": "<b>NASCONDE</b> (colora di rosso)",
    "<b>How to read the image:</b> <span style='color:#ff6b6b'><b>red</b></span> areas will be <b>hidden</b> "
    "in the camera, everything else will be visible.":
        "<b>Come leggere l'immagine:</b> le zone <span style='color:#ff6b6b'><b>rosse</b></span> saranno "
        "<b>nascoste</b> nella camera, tutto il resto sarà visibile.",
    "<b>Left mouse button:</b> {left}. &nbsp; <b>Right button:</b> {right}.":
        "<b>Tasto sinistro del mouse:</b> {left}. &nbsp; <b>Tasto destro:</b> {right}.",
    "<b>Brush:</b> hold the button down and drag to paint; set the size with the «Brush» slider.":
        "<b>Pennello:</b> tieni premuto il tasto e trascina per dipingere; la dimensione si regola con il "
        "cursore «Pennello».",
    "<b>Rectangle:</b> drag from one corner to the opposite one; the rectangle is filled when you release the "
    "button. Hold <b>Ctrl</b> for a square.":
        "<b>Rettangolo:</b> trascina da un angolo a quello opposto; quando rilasci il tasto, il rettangolo viene "
        "riempito. Tieni premuto <b>Ctrl</b> per un quadrato.",
    "<b>Ellipse:</b> drag to draw the box that contains the ellipse; the ellipse is filled when you release the "
    "button. Hold <b>Ctrl</b> for a circle.":
        "<b>Ellisse:</b> trascina per disegnare il riquadro che contiene l'ellisse; quando rilasci il tasto, "
        "l'ellisse viene riempita. Tieni premuto <b>Ctrl</b> per un cerchio.",
    "<b>Zoom:</b> Ctrl + mouse wheel, or «Fit» and «100%». &nbsp; <b>Undo:</b> Ctrl+Z. &nbsp; "
    "The dashed yellow frame, if present, is the layer's crop.":
        "<b>Zoom:</b> Ctrl + rotella del mouse, oppure «Adatta» e «100%». &nbsp; <b>Annulla:</b> Ctrl+Z. &nbsp; "
        "Il riquadro giallo tratteggiato, se presente, è il crop del layer.",
    # monitors
    "Monitor {index}: {width}×{height}": "Monitor {index}: {width}×{height}",
    " (primary)": " (principale)",
    # source status
    "webcam not found: {name}": "webcam non trovata: {name}",
    "webcam not available (maybe in use by another app): {name}":
        "webcam non disponibile (forse in uso da un'altra app): {name}",
    "webcam disconnected: {name}": "webcam scollegata: {name}",
    "window not found: {name}": "finestra non trovata: {name}",
    "image not found: {path}": "immagine non trovata: {path}",
    "capture failed: {error}": "cattura non riuscita: {error}",
    "monitor {index} not found": "monitor {index} non trovato",
    # virtual camera
    "The virtual camera is not installed: reinstall simpleVCam.":
        "La virtual camera non è installata: reinstalla simpleVCam.",
    "The virtual camera is not installed: run scripts\\install_vcam.ps1 as administrator.":
        "La virtual camera non è installata: esegui scripts\\install_vcam.ps1 come amministratore.",
    "Width and height must be even.": "Larghezza e altezza devono essere pari.",
    "Cannot write {path}: {error}": "Impossibile scrivere {path}: {error}",
    "Starting the virtual camera failed (HRESULT 0x{hr:08X}).":
        "Avvio della virtual camera fallito (HRESULT 0x{hr:08X}).",
    # scene and presets
    "unknown source type: {type}": "tipo di sorgente sconosciuto: {type}",
    "the mask must be a single-channel image": "la mask deve essere un'immagine a un canale",
    "cannot encode {name}": "impossibile codificare {name}",
    "preset version {version} not supported (maximum {maximum})":
        "preset versione {version} non supportato (massimo {maximum})",
    "unreadable mask: {path}": "mask non leggibile: {path}",
}
