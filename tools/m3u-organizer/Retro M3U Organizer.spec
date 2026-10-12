# -*- mode: python ; coding: utf-8 -*-


from pathlib import Path

app_dir = Path(SPECPATH)

a = Analysis(
    [str(app_dir / 'run.py')],
    pathex=[str(app_dir)],
    binaries=[],
    datas=[(str(app_dir / 'images'), 'images')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Retro M3U Organizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(app_dir / 'images' / 'm3u-logo.ico')],
)
