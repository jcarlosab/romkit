import hashlib
import json
import struct
import zlib

import pytest

from romkit_core.analysis.images import export_images, image_ranges
from romkit_core.analysis.inventory import inventory
from romkit_core.tasks import TaskCancelled
from romkit_core.workspace import WorkspaceManager


def png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0\xff\0\0")) + chunk(b"IEND", b""))


def test_embedded_pngs_export_with_exact_bytes_origin_and_no_source_changes(tmp_path):
    workspace = WorkspaceManager(tmp_path / "workspace")
    source = workspace.layout.path("extracted", "PSP_GAME/ASSET.BIN", create_parent=True)
    raw = b"prefix" + png() + b"between" + png() + b"trailer"
    source.write_bytes(raw)
    resources = inventory(workspace.layout.area("extracted"))
    destination = tmp_path / "out"
    destination.mkdir()
    result = export_images(resources, workspace, destination)
    assert result.count == 1 and result.duplicates == 1
    manifest = json.loads((result.path / "imagenes.json").read_text())["images"]
    assert len(manifest) == 2  # Both occurrences retain their provenance.
    assert manifest[0]["offset"] == len(b"prefix")
    for image in manifest:
        assert (result.path / image["file"]).read_bytes() == png()
        assert image["sha256"] == hashlib.sha256(png()).hexdigest()
    assert source.read_bytes() == raw


def test_corrupt_and_truncated_pngs_are_ignored():
    corrupt = bytearray(png())
    corrupt[20] ^= 1
    assert list(image_ranges(bytes(corrupt))) == []
    assert list(image_ranges(png()[:-5])) == []


def test_cancelled_export_leaves_destination_untouched(tmp_path):
    workspace = WorkspaceManager(tmp_path / "workspace")
    source = workspace.layout.path("extracted", "ICON.PNG", create_parent=True)
    source.write_bytes(png())
    destination = tmp_path / "out"
    destination.mkdir()
    (destination / "existing.txt").write_text("keep")
    def cancel(value):
        if value.message.startswith("Guardando"):
            raise TaskCancelled()
    with pytest.raises(TaskCancelled):
        export_images(inventory(workspace.layout.area("extracted")), workspace, destination, progress=cancel)
    assert [path.name for path in destination.iterdir()] == ["existing.txt"]
