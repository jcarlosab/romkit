"""Common Qt startup for the two independent application processes."""

import sys
import json
from pathlib import Path
from collections.abc import Callable, Sequence

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import QTimer, qVersion

from romkit_core import __version__


def run(window_factory: Callable[[], QWidget], argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv if argv is None else argv)
    smoke_report = None
    if '--smoke-test' in arguments:
        index = arguments.index('--smoke-test')
        if index + 1 >= len(arguments):
            raise ValueError('--smoke-test necesita una ruta para el informe')
        smoke_report = Path(arguments[index + 1])
        del arguments[index:index + 2]
    app = QApplication(arguments)
    app.setOrganizationName("ROMKit")
    app.setApplicationVersion(__version__)
    window = window_factory()
    app.setApplicationName(window.windowTitle())
    app.setWindowIcon(window.windowIcon())
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            window.windowTitle().split(' · v')[0].replace(" ", "."))
    window.show()
    if smoke_report is not None:
        def check_ready():
            ready = window.isVisible() and window.windowHandle() is not None
            if ready:
                smoke_report.write_text(json.dumps({'ready': True, 'title': window.windowTitle(),
                    'qt': qVersion(), 'platform': app.platformName(), 'version': __version__,
                    'frozen': bool(getattr(sys, 'frozen', False))}), encoding='utf-8')
            window.close()
            app.exit(0 if ready else 1)
        QTimer.singleShot(200, check_ready)
    return app.exec()
