"""Build controlled ISO images in tests; no commercial game data."""
from io import BytesIO

import pycdlib


def make_iso(path, *, psp=True, extra_files=None):
    files = {"README.TXT": b"Generic ISO fixture\x00"}
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3)
    buffers = []
    if psp:
        for directory in ("/PSP_GAME", "/PSP_GAME/SYSDIR", "/PSP_GAME/USRDIR", "/PSP_GAME/EMPTY"):
            iso.add_directory(directory)
        files.update({"PSP_GAME/PARAM.SFO": b"\x00PSFfixture", "PSP_GAME/SYSDIR/EBOOT.BIN": b"\x7fELFfixture",
                      "PSP_GAME/USRDIR/TEXT.BIN": b"\xff\x00Hello traveller!\x00Good morning!\x00",
                      "PSP_GAME/USRDIR/UNKNOWN.XYZ": b"\xff\x00\x01\x02"})
    files.update(extra_files or {})
    for name, data in files.items():
        buffer = BytesIO(data)
        buffers.append(buffer)
        iso.add_fp(buffer, len(data), "/" + name + ";1")
    iso.write(str(path))
    iso.close()
    return files
