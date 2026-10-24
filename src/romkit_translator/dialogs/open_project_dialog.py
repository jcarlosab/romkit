from pathlib import Path
from PySide6.QtWidgets import QFileDialog


def choose_project(parent):
    path = QFileDialog.getExistingDirectory(parent, "Abrir proyecto de traducción")
    return Path(path) if path else None
