import sys
import os
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))


@pytest.fixture(scope="session")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()
