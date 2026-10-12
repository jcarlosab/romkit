# Build from the repository root:
# .venv\Scripts\python.exe -m PyInstaller --noconfirm tools\scraper\romkit_scraper.spec
from pathlib import Path

tools = Path(SPECPATH)
a = Analysis(
    [str(tools / "romkit_scraper.py")],
    pathex=[str(tools)],
    binaries=[],
    datas=[(str(tools / "assets"), "assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6.QtWidgets", "PySide6.QtNetwork", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="ROMKit Scraper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(tools / "assets" / "romkit.ico"),
)
