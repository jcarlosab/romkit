from pathlib import Path

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt


def application_icon(name="studio"):
    source = QIcon(str(Path(__file__).parent / "assets" / f"{name}.svg"))
    pixels = source.pixmap(16, 16).toImage()
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(pixels.scaled(size, size,
            Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)))
    return icon
