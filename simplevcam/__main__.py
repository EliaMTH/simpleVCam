import ctypes
import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from simplevcam.ui.main_window import MainWindow
from simplevcam.ui.theme import apply_dark_theme

ICON = Path(__file__).resolve().parent / "assets" / "simplevcam.ico"


def main() -> int:
    # own taskbar identity (otherwise, from sources, Windows groups it with python.exe)
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("simpleVCam")
    app = QApplication(sys.argv)
    app.setApplicationName("simpleVCam")
    app.setWindowIcon(QIcon(str(ICON)))
    apply_dark_theme(app)
    # standard dialog buttons ("Cancel", ...) in the system language
    translator = QTranslator(app)
    if translator.load(QLocale.system(), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)

    if "--smoke-test" in sys.argv:
        from simplevcam.smoke import run

        i = sys.argv.index("--smoke-test")
        return run(sys.argv[i + 1] if i + 1 < len(sys.argv) else None)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
