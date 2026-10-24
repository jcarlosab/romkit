from io import BytesIO
import gzip
import json
import struct
import zipfile
import zlib

import pytest

from graphics_builder import make_gim, make_bnd
from pokapoka_builder import make_archive
from romkit_core.analysis.containers import Traversal, walk_payloads
from romkit_core.analysis.gim import decode_gim, gim_end
from romkit_core.analysis.images import export_images
from romkit_core.analysis.inventory import inventory
from romkit_core.workspace import WorkspaceManager


def rgba(png):
    offset, idat = 8, b""
    while offset < len(png):
        size = struct.unpack_from(">I", png, offset)[0]
        if png[offset + 4:offset + 8] == b"IDAT":
            idat += png[offset + 8:offset + 8 + size]
        offset += 12 + size
    return zlib.decompress(idat)


@pytest.mark.parametrize("fmt,pixels,expected", [
    (0, struct.pack("<HH", 31, 63 << 5), b"\xff\0\0\xff\0\xff\0\xff"),
    (1, struct.pack("<HH", 0x801f, 0x7c00), b"\xff\0\0\xff\0\0\xff\0"),
    (2, struct.pack("<HH", 0xf00f, 0xff00), b"\xff\0\0\xff\0\0\xff\xff"),
    (3, b"\xff\0\0\xff\0\xff\0\xff", b"\xff\0\0\xff\0\xff\0\xff"),
])
def test_gim_direct_color_formats(fmt, pixels, expected):
    image = decode_gim(make_gim(fmt, pixels=pixels))[0]
    assert (image.width, image.height) == (2, 1)
    assert rgba(image.png) == b"\0" + expected


@pytest.mark.parametrize("fmt,pixels", [(4, b"\x10"), (5, b"\0\1"), (6, b"\0\0\1\0"), (7, struct.pack("<II", 0, 1))])
def test_gim_indexed_formats(fmt, pixels):
    colors = [b"\xff\0\0\xff", b"\0\xff\0\xff"]
    image = decode_gim(make_gim(fmt, pixels=pixels, palette=colors))[0]
    assert rgba(image.png) == b"\0" + b"".join(colors)


def test_swizzle_is_reversed_without_cropping_or_color_changes():
    linear = bytes(component for y in range(8) for x in range(8) for component in (x * 20, y * 20, 0, 255))
    swizzled = bytearray(256)
    for y in range(8):
        for x in range(0, 32, 16):
            start = x // 16 * 128 + y * 16
            swizzled[start:start + 16] = linear[y * 32 + x:y * 32 + x + 16]
    image = decode_gim(make_gim(3, width=8, height=8, pixels=swizzled, order=1))[0]
    expected = b"".join(b"\0" + linear[y * 32:(y + 1) * 32] for y in range(8))
    assert rgba(image.png) == expected


def test_invalid_gim_is_bounded_and_rejected():
    data = make_gim()
    assert gim_end(data[:-1], 0) is None
    modified = bytearray(data)
    struct.pack_into("<HH", modified, 48 + 16 + 8, 65535, 65535)
    with pytest.raises(ValueError):
        decode_gim(modified)


def test_nested_zip_gzip_bnd_gim_exports_png_and_provenance(tmp_path):
    memory = BytesIO()
    with zipfile.ZipFile(memory, "w") as archive:
        archive.writestr("../../unsafe.gz", gzip.compress(make_bnd("icon.gim", make_gim())))
    workspace = WorkspaceManager(tmp_path / "workspace")
    source = workspace.layout.path("extracted", "GRAPHICS.DAT", create_parent=True)
    source.write_bytes(memory.getvalue())
    destination = tmp_path / "out"
    destination.mkdir()
    result = export_images(inventory(workspace.layout.area("extracted")), workspace, destination)
    assert result.count == 1 and result.containers == 3 and result.warnings == 0
    manifest = json.loads((result.path / "imagenes.json").read_text())["images"]
    assert "!zip/" in manifest[0]["source"] and "!bnd/" in manifest[0]["source"]
    assert (result.path / manifest[0]["file"]).read_bytes().startswith(b"\x89PNG")
    assert not (tmp_path / "unsafe.gz").exists()


def test_traversal_limits_prevent_bombs_and_unbounded_nesting():
    budget = Traversal(max_expanded=100)
    assert list(walk_payloads(zlib.compress(bytes(10000)), "bomb", budget)) == []
    assert budget.warnings
    budget = Traversal(max_depth=1)
    assert list(walk_payloads(gzip.compress(gzip.compress(make_gim())), "nested", budget)) == []
    assert "profundidad" in budget.warnings[0]["message"]


def test_indexed_fat_bhd_bundle_opens_compressed_graphics(tmp_path):
    workspace = WorkspaceManager(tmp_path / "workspace")
    directory = workspace.layout.path("extracted", "PSP_GAME/USRDIR", create_parent=True)
    make_archive(directory, make_bnd("menu.gim", make_gim()), name="menu.bnd")
    destination = tmp_path / "out"
    destination.mkdir()
    result = export_images(inventory(workspace.layout.area("extracted")), workspace, destination)
    assert result.count == 1 and result.containers == 2 and result.warnings == 0
    manifest = json.loads((result.path / "imagenes.json").read_text())["images"]
    assert "POKAPOKA.BND.contents/00000/menu.bnd!bnd/00000-menu.gim" in manifest[0]["source"]


def test_unsupported_bnd_layout_falls_back_to_verified_embedded_images():
    data = b"BND\0" + bytes(28) + make_gim()
    traversal = Traversal()
    leaves = list(walk_payloads(data, "unsupported.bnd", traversal))
    assert leaves == [("unsupported.bnd", data)]
    assert traversal.warnings
