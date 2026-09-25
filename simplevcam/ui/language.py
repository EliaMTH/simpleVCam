"""UI language: the choice saved between sessions and Qt's own translations (standard dialog buttons)."""
from __future__ import annotations

from PySide6.QtCore import QLibraryInfo, QLocale, QSettings, QTranslator
from PySide6.QtWidgets import QApplication

from ..i18n import LANGUAGES, set_language

_qt_translator: QTranslator | None = None


def _settings() -> QSettings:
    return QSettings("simpleVCam", "simpleVCam")  # HKCU\Software\simpleVCam


def initial_language() -> str:
    """The saved choice, or the Windows language on the first run (English if not supported)."""
    saved = _settings().value("language", "")
    if saved in LANGUAGES:
        return saved
    return "it" if QLocale.system().language() == QLocale.Language.Italian else "en"


def apply_language(code: str, save: bool = False) -> None:
    """Switches the app texts and the Qt standard texts ("OK", "Cancel", ...) to `code`."""
    global _qt_translator
    set_language(code)
    app = QApplication.instance()
    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator = None
    if code != "en":
        translator = QTranslator(app)
        if translator.load(f"qtbase_{code}", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
            app.installTranslator(translator)
            _qt_translator = translator
    if save:
        _settings().setValue("language", code)
