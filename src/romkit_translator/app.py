from collections.abc import Sequence

from romkit_core.app import run
from romkit_translator.windows.main_window import MainWindow


def main(argv: Sequence[str] | None = None) -> int:
    return run(MainWindow, argv)
