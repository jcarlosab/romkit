from collections.abc import Sequence

from romkit_core.app import run
from romkit_studio.windows.main_window import MainWindow
from romkit_studio.services.controller import StudioController


def main(argv: Sequence[str] | None = None) -> int:
    def create_window():
        window = MainWindow()
        window.controller = StudioController(window)
        return window
    return run(create_window, argv)
