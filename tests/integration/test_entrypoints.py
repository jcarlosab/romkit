import os
from pathlib import Path
import subprocess
import sys
import json
from romkit_core import __version__

import pytest


@pytest.mark.integration
@pytest.mark.parametrize("name,title", [("romkit-studio", "ROMKit Studio"), ("romkit-translator", "ROMKit Translator")])
def test_installed_entrypoint_shows_window_and_exits(name, title):
    # Each installed command runs in a fresh process with its own QApplication.
    script = f'''
from importlib.metadata import distribution
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
entrypoint = next(ep for ep in distribution("romkit").entry_points if ep.name == {name!r})
def check_window():
    app = QApplication.instance()
    windows = [w for w in app.topLevelWidgets() if w.isVisible()]
    app.exit(0 if any(w.windowTitle() == {f'{title} · v{__version__}'!r} for w in windows) else 1)
original_exec = QApplication.exec
def checked_exec(self):
    QTimer.singleShot(100, check_window)
    return original_exec()
QApplication.exec = checked_exec
raise SystemExit(entrypoint.load()([]))
'''
    result = subprocess.run([sys.executable, "-c", script], env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, capture_output=True, text=True, timeout=30, cwd=Path(__file__).parents[2])
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration
@pytest.mark.parametrize("command", ["romkit-studio", "romkit-translator"])
def test_console_launcher_exists(command):
    assert (Path(sys.executable).parent / (command + (".exe" if os.name == "nt" else ""))).is_file()


@pytest.mark.parametrize('module', ['romkit_studio', 'romkit_translator'])
def test_smoke_marker_requires_real_qt_window(module, tmp_path):
    marker = tmp_path / 'ready.json'
    result = subprocess.run([sys.executable, '-m', module, '--smoke-test', str(marker)],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    report = json.loads(marker.read_text(encoding='utf-8'))
    assert report['ready'] is True and report['platform'] == 'offscreen'
    assert report['qt'] and report['title'].startswith('ROMKit')
